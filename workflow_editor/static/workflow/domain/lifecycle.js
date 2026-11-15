import { portsForNode } from './node-contract.js';

// A static editor preview: never annotate or mutate the serialized workflow.
export function compileLifecycles(workflow) {
  const nodes = workflow.nodes || [];
  const connections = workflow.connections || [];
  const byId = new Map(nodes.map((node) => [node.id, node]));
  const outgoing = new Map(nodes.map((node) => [node.id, []]));
  const nodeScopes = new Map();
  const outputScopes = new Map();
  const scopes = [];
  const errors = [];
  const invalidConnections = new Set();
  const fail = (message, nodeId, edge) => {
    errors.push({ message, nodeId, connection: edge });
    if (edge) invalidConnections.add(edge);
  };
  const name = (node) => node.name || node.id;
  const ports = (node) => portsForNode({ ...node, ...node.arguments })
    .filter((port) => port.type === 'control');
  const addScope = (parentId, kind, label, ownerId, portId) => {
    const id = `L${scopes.length}`;
    const parent = scopes.find((scope) => scope.id === parentId);
    const hue = (205 + scopes.length * 137.508) % 360;
    const scope = {
      id, parentId, kind, label, ownerId, portId,
      depth: parent ? parent.depth + 1 : 0,
      path: [...(parent?.path || []), label],
      color: `hsl(${hue.toFixed(1)} 45% 36%)`,
      fill: `hsl(${hue.toFixed(1)} 65% 93%)`,
    };
    scopes.push(scope);
    return id;
  };
  const root = addScope(null, 'root', 'Workflow', null, null);
  if (byId.size !== nodes.length) fail('节点 ID 重复，无法编译控制树。');
  const inputs = nodes.filter((node) => node.type === 'input');
  if (inputs.length !== 1) fail('必须恰有一个 Input 节点。');
  for (const edge of connections) {
    if (!byId.has(edge.fromId) || !byId.has(edge.toId)) {
      fail('连线引用了不存在的节点。', null, edge);
      continue;
    }
    if (edge.type !== 'control') continue;
    const source = byId.get(edge.fromId);
    const target = byId.get(edge.toId);
    if (!ports(source).some((port) => port.direction === 'output' && port.id === edge.fromPortId)
      || !ports(target).some((port) => port.direction === 'input' && port.id === edge.toPortId)) {
      fail('控制连线端口无效。', source.id, edge);
      continue;
    }
    outgoing.get(edge.fromId).push(edge);
  }

  const active = new Set();
  const returnedLoops = new Set();
  function visit(nodeId, scopeId, loopId = null) {
    const node = byId.get(nodeId);
    if (active.has(nodeId)) {
      fail(`「${name(node)}」形成了非 Foreach loop-in 回边的环。`, nodeId);
      return;
    }
    if (nodeScopes.has(nodeId)) {
      fail(`「${name(node)}」有多个控制入口；不允许分支汇合或共享节点。`, nodeId);
      return;
    }
    nodeScopes.set(nodeId, scopeId);
    active.add(nodeId);
    const controls = ports(node).filter((port) => port.direction === 'output');
    const edges = outgoing.get(nodeId);
    // Match the existing rule: no branching node (including nested foreach) in a loop body.
    if (loopId && (controls.length > 1 || node.type === 'router')) {
      fail(`Foreach 循环体内不允许多分支节点「${name(node)}」。`, nodeId);
    }
    if (loopId && node.type === 'output') {
      fail(`循环体必须返回 Foreach 的 loop-in，不能在「${name(node)}」结束。`, nodeId);
    }
    const successors = new Map();
    for (const edge of edges) {
      if (successors.has(edge.fromPortId)) {
        fail(`「${name(node)}」的控制出口 ${edge.fromPortId} 有多个后继。`, nodeId, edge);
      } else successors.set(edge.fromPortId, edge);
    }
    for (const port of controls) {
      let childScope = scopeId;
      let childLoop = loopId;
      if (node.type === 'foreach' && port.id === 'loop-out') {
        childScope = addScope(scopeId, 'loop', `${name(node)} / 循环体`, nodeId, port.id);
        outputScopes.set(nodeId, { 'item-out': childScope });
        childLoop = nodeId;
      } else if (node.type !== 'foreach' && (node.type === 'router' || controls.length > 1)) {
        childScope = addScope(scopeId, 'branch', `${name(node)} / ${port.label}`, nodeId, port.id);
        if (node.type === 'json_tool') {
          const dataPort = port.id === 'error-out' ? 'error-json' : 'result-json';
          outputScopes.set(nodeId, { ...outputScopes.get(nodeId), [dataPort]: childScope });
        }
      }
      const edge = successors.get(port.id);
      if (!edge) {
        if (!(node.type === 'json_tool' && port.id === 'error-out')) {
          fail(`「${name(node)}」的控制出口 ${port.label} 未连接。`, nodeId);
        }
        continue;
      }
      const target = byId.get(edge.toId);
      if (target.type === 'foreach' && edge.toPortId === 'loop-in') {
        if (target.id !== childLoop) {
          fail(`loop-in 只能接收自己循环体的回边：「${name(target)}」。`, nodeId, edge);
        } else returnedLoops.add(target.id);
        continue;
      }
      visit(edge.toId, childScope, childLoop);
    }
    active.delete(nodeId);
  }
  if (inputs.length === 1) visit(inputs[0].id, root);
  for (const node of nodes) {
    if (!nodeScopes.has(node.id)) fail(`「${name(node)}」无法从 Input 到达。`, node.id);
    if (node.type === 'foreach' && nodeScopes.has(node.id) && !returnedLoops.has(node.id)) {
      fail(`「${name(node)}」缺少循环体返回 loop-in 的连接。`, node.id);
    }
  }
  const structureValid = errors.length === 0;
  const scopeById = new Map(scopes.map((scope) => [scope.id, scope]));
  const visible = (source, target) => {
    for (let cursor = target; cursor != null; cursor = scopeById.get(cursor)?.parentId) {
      if (cursor === source) return true;
    }
    return false;
  };
  if (structureValid) {
    for (const edge of connections.filter((connection) => connection.type !== 'control')) {
      const source = outputScopes.get(edge.fromId)?.[edge.fromPortId] || nodeScopes.get(edge.fromId);
      const target = nodeScopes.get(edge.toId);
      if (!visible(source, target)) {
        fail(`数据越界：${name(byId.get(edge.fromId))}.${edge.fromPortId} (${source}) → ${name(byId.get(edge.toId))}.${edge.toPortId} (${target})；只允许同生命周期或父级向子级传值。`, edge.toId, edge);
      }
    }
  }
  return { scopes, nodeScopes, outputScopes, errors, invalidConnections, structureValid };
}

// Positions are presentation-only: dragging should not invalidate a compilation.
export function lifecycleFingerprint(workflow) {
  return JSON.stringify({
    nodes: workflow.nodes.map(({ x, y, ...node }) => node),
    connections: workflow.connections,
  });
}
