const NODE_TYPES = new Set(['input', 'output', 'router', 'construct_message', 'construct_content', 'construct_list', 'foreach', 'llm', 'tool', 'tool_call', 'workflow']);
let idSequence = 0;

const initialNodes = [
  { id: 'input', type: 'input', name: 'Input', x: 52, y: 238 },
  { id: 'output', type: 'output', name: 'Output', x: 310, y: 238 },
];

const initialConnections = [
  { id: 'control-input-output', fromId: 'input', fromPortId: 'control-out', toId: 'output', toPortId: 'control-in', type: 'control' },
];

export const state = {
  name: 'workflow',
  nodes: structuredClone(initialNodes),
  connections: structuredClone(initialConnections),
  input_ports: [],
  output_ports: [],
  workflow_nodes: [],
  selectedId: 'input',
  connectionDrag: null,
};

export function nodeById(id) {
  return state.nodes.find((node) => node.id === id);
}

export function createWorkflowId(prefix) {
  idSequence += 1;
  return `${prefix}-${Date.now()}-${idSequence}`;
}

function nextNodePosition() {
  const positions = [];
  for (let row = 0; row < 4; row += 1) {
    for (let column = 0; column < 3; column += 1) {
      positions.push({ x: 52 + column * 258, y: 72 + row * 150 });
    }
  }
  const availablePosition = positions.find((position) => state.nodes.every((node) => Math.abs(node.x - position.x) >= 210 || Math.abs(node.y - position.y) >= 125));
  if (availablePosition) return availablePosition;

  const overflowIndex = state.nodes.length - positions.length;
  const column = overflowIndex % 6;
  const row = Math.floor(overflowIndex / 6) + 4;
  return { x: 52 + column * 258, y: 72 + row * 150 };
}

export function addNode(type, configuration = null) {
  if (!['output', 'router', 'construct_message', 'construct_content', 'construct_list', 'foreach', 'llm', 'tool', 'tool_call', 'workflow'].includes(type)) return;
  const number = state.nodes.filter((node) => node.type === type).length + 1;
  const position = nextNodePosition();
  const node = type === 'router'
    ? { id: createWorkflowId('router'), type, name: `Router ${number}`, branches: [{ id: createWorkflowId('branch'), name: '分支 1' }, { id: createWorkflowId('branch'), name: '分支 2' }], ...position }
    : type === 'output'
      ? {
          id: createWorkflowId('output'),
          type,
          name: `Output ${number}`,
          workflowPorts: metadataPorts(configuration?.output_ports),
          ...position,
        }
    : type === 'construct_message'
      ? { id: createWorkflowId('construct-message'), type, name: `构造 Message ${number}`, role: 'user', ...position }
    : type === 'construct_content'
      ? { id: createWorkflowId('construct-content'), type, name: `构造 Content ${number}`, append_items: [{ type: 'fixed', value: '' }], dataInputPorts: [], ...position }
    : type === 'construct_list'
      ? { id: createWorkflowId('construct-list'), type, name: `构造列表 ${number}`, item_type: 'content', initial_value_count: 1, dataInputPorts: ['content-in-0'], ...position }
    : type === 'foreach'
      ? { id: createWorkflowId('foreach'), type, name: `遍历列表 ${number}`, item_type: 'content', ...position }
    : type === 'llm'
      ? { id: createWorkflowId('llm'), type, name: `LLM ${number}`, model: '', prompt: '处理输入并返回结果。', dataInputPorts: ['message-in-0'], tools: [], think: false, tool_calls: false, ...position }
      : type === 'tool_call'
        ? { id: createWorkflowId('tool-call'), type, name: `Tool Call ${number}`, ...position }
      : type === 'tool'
        ? { id: createWorkflowId('tool'), type, name: `Tool ${number}`, tool: '', parameters: [], ...position }
        : type === 'workflow' && configuration
          ? {
              id: createWorkflowId('workflow'),
              type,
              name: configuration.name || `Workflow ${number}`,
              workflow_id: configuration.workflow_id,
              workflow_name: configuration.name || configuration.workflow_id,
              input_ports: structuredClone(configuration.input_ports || []),
              output_ports: structuredClone(configuration.output_ports || []),
              ...position,
            }
        : null;
  if (!node) return;
  state.nodes.push(node);
  state.selectedId = node.id;
}

export function deleteNode(id) {
  if (id === 'input') return;
  state.nodes = state.nodes.filter((node) => node.id !== id);
  state.connections = state.connections.filter((connection) => connection.fromId !== id && connection.toId !== id);
  state.selectedId = state.nodes[0].id;
}

export function workflowSnapshot() {
  return structuredClone({
    name: state.name,
    input_ports: state.input_ports,
    output_ports: state.output_ports,
    workflow_nodes: state.workflow_nodes,
    nodes: state.nodes,
    connections: state.connections,
  });
}

function draftStorageKey(workflowId) {
  return `aagent.workflow.draft.v1.${workflowId}`;
}

export function saveDraft(workflowId) {
  if (!workflowId) return false;
  localStorage.setItem(draftStorageKey(workflowId), JSON.stringify(workflowSnapshot()));
  return true;
}

export function loadDraft(workflowId) {
  if (!workflowId) return false;
  const raw = localStorage.getItem(draftStorageKey(workflowId));
  if (!raw) return false;
  try {
    return loadSnapshot(JSON.parse(raw));
  } catch (error) {
    localStorage.removeItem(draftStorageKey(workflowId));
    return false;
  }
}

export function resetDraft(workflowId) {
  if (!workflowId) return false;
  localStorage.removeItem(draftStorageKey(workflowId));
  return true;
}

export function resetWorkflow(metadata = null) {
  return loadSnapshot({ nodes: initialNodes, connections: initialConnections }, metadata);
}

function metadataPorts(ports) {
  return (Array.isArray(ports) ? ports : []).flatMap((port) => {
    if (!port || typeof port.name !== 'string' || !['content', 'message', 'list-content', 'list-message'].includes(port.type)) return [];
    return [{ id: `workflow:${port.name}`, name: port.name.slice(0, 80), type: port.type }];
  });
}

function callableWorkflowMetadata(saved) {
  const declarations = Array.isArray(saved?.workflow_nodes)
    ? saved.workflow_nodes
    : Array.isArray(saved?.callable_workflows)
      ? saved.callable_workflows
    : (Array.isArray(saved?.nodes) ? saved.nodes : []).filter((node) => node?.type === 'workflow');
  const names = new Set();
  return declarations.flatMap((workflow) => {
    const name = typeof workflow?.name === 'string' && workflow.name.trim()
      ? workflow.name.trim().slice(0, 120)
      : typeof workflow?.workflow_name === 'string' && workflow.workflow_name.trim()
        ? workflow.workflow_name.trim().slice(0, 120)
        : typeof workflow?.workflow_id === 'string' ? workflow.workflow_id.trim().slice(0, 120) : '';
    const normalizedName = name.toLocaleLowerCase();
    if (!name || names.has(normalizedName)) return [];
    names.add(normalizedName);
    return [{
      workflow_id: typeof workflow.workflow_id === 'string' && workflow.workflow_id.trim() ? workflow.workflow_id.trim().slice(0, 120) : name,
      name,
      input_ports: metadataPorts(workflow.input_ports).map(({ id, ...port }) => port),
      output_ports: metadataPorts(workflow.output_ports).map(({ id, ...port }) => port),
    }];
  });
}

export function loadSnapshot(saved, metadata = null) {
  try {
    const savedNodes = Array.isArray(saved) ? saved : saved?.nodes;
    if (!Array.isArray(savedNodes)) return false;
    state.name = typeof (metadata?.name ?? saved?.name) === 'string' ? (metadata?.name ?? saved?.name).slice(0, 120) : '';
    const inputPorts = metadataPorts(metadata?.input_ports ?? saved?.input_ports);
    const outputPorts = metadataPorts(metadata?.output_ports ?? saved?.output_ports);
    state.input_ports = inputPorts.map(({ id, ...port }) => port);
    state.output_ports = outputPorts.map(({ id, ...port }) => port);
    state.workflow_nodes = callableWorkflowMetadata(saved);
    const callableWorkflows = new Map(state.workflow_nodes.flatMap((workflow) => [[workflow.workflow_id, workflow], [workflow.name, workflow]]));
    const ids = new Set();
    const normalizedNodes = savedNodes.flatMap((node) => {
      if (!node || typeof node.id !== 'string' || ids.has(node.id) || !NODE_TYPES.has(node.type)) return [];
      ids.add(node.id);
      const normalized = {
        id: node.id,
        type: node.type,
        name: typeof node.name === 'string' ? node.name.slice(0, 30) : node.type.toUpperCase(),
        x: Number.isFinite(node.x) ? Math.max(12, node.x) : 52,
        y: Number.isFinite(node.y) ? Math.max(12, node.y) : 72,
      };
      if (node.type === 'input' || node.type === 'output') {
        const metadataPortList = node.type === 'input' ? inputPorts : outputPorts;
        const portIds = new Set();
        normalized.workflowPorts = metadataPortList.flatMap((port) => {
          if (!port || typeof port.id !== 'string' || !port.id.startsWith('workflow:') || portIds.has(port.id)) return [];
          if (!['content', 'message', 'list-content', 'list-message'].includes(port.type)) return [];
          portIds.add(port.id);
          return [{
            id: port.id,
            name: typeof port.name === 'string' ? port.name.slice(0, 80) : port.id.slice(9),
            type: port.type,
          }];
        });
      }
      if (node.type === 'router') {
        const branchIds = new Set();
        normalized.branches = (Array.isArray(node.branches) ? node.branches : []).flatMap((branch) => {
          if (!branch || typeof branch.id !== 'string' || branchIds.has(branch.id)) return [];
          branchIds.add(branch.id);
          return [{ id: branch.id, name: typeof branch.name === 'string' ? branch.name.slice(0, 30) : '分支' }];
        });
        if (!normalized.branches.length) normalized.branches.push({ id: createWorkflowId('branch'), name: '分支 1' });
      }
      if (node.type === 'llm') {
        normalized.model = typeof node.model === 'string' ? node.model : 'gpt-5';
        normalized.prompt = typeof node.prompt === 'string' ? node.prompt.slice(0, 500) : '';
        const legacyCount = Number.isInteger(node.contextCount)
          ? node.contextCount
          : Array.isArray(node.inputs) ? node.inputs.length : 1;
        const declaredCount = Array.isArray(node.dataInputPorts)
          ? node.dataInputPorts.filter((portId) => typeof portId === 'string' && /^(?:content|message)-in-\d+$/.test(portId)).length
          : legacyCount;
        normalized.dataInputPorts = Array.from(
          { length: Math.min(20, Math.max(1, declaredCount)) },
          (_, index) => `message-in-${index}`,
        );
        normalized.think = node.think === true;
        normalized.tool_calls = node.tool_calls === true;
        normalized.tools = normalized.tool_calls && Array.isArray(node.tools)
          ? [...new Set(node.tools.filter((tool) => typeof tool === 'string' && tool))]
          : [];
      }
      if (node.type === 'construct_message') {
        normalized.role = ['user', 'system', 'assistant'].includes(node.role) ? node.role : 'user';
      }
      if (node.type === 'construct_content') {
        normalized.append_items = Array.isArray(node.append_items) && node.append_items.length
          ? node.append_items.flatMap((item, index) => item?.type === 'port'
            ? [{ type: 'port', port_id: typeof item.port_id === 'string' && item.port_id ? item.port_id : `append-in-${index}` }]
            : item?.type === 'fixed' ? [{ type: 'fixed', value: typeof item.value === 'string' ? item.value.slice(0, 100000) : '' }] : [])
          : [{ type: 'port', port_id: 'append-in-0' }];
        normalized.dataInputPorts = normalized.append_items
          .filter((item) => item.type === 'port')
          .map((item) => item.port_id);
      }
      if (node.type === 'construct_list') {
        normalized.item_type = ['content', 'message'].includes(node.item_type) ? node.item_type : 'content';
        normalized.initial_value_count = Number.isInteger(node.initial_value_count)
          ? Math.min(20, Math.max(0, node.initial_value_count))
          : 1;
        normalized.dataInputPorts = Array.from(
          { length: normalized.initial_value_count },
          (_, index) => `${normalized.item_type}-in-${index}`,
        );
      }
      if (node.type === 'foreach') {
        normalized.item_type = ['content', 'message'].includes(node.item_type) ? node.item_type : 'content';
      }
      if (node.type === 'tool') {
        normalized.tool = typeof node.tool === 'string' ? node.tool : '';
        normalized.parameters = Array.isArray(node.parameters)
          ? [...new Set(node.parameters.filter((parameter) => typeof parameter === 'string' && parameter))]
          : [];
      }
      if (node.type === 'workflow') {
        if (typeof node.workflow_id !== 'string' || !node.workflow_id) return [];
        const declaration = callableWorkflows.get(node.workflow_id);
        normalized.workflow_id = declaration?.name || node.workflow_id;
        normalized.workflow_name = declaration?.name || (typeof node.workflow_name === 'string' ? node.workflow_name.slice(0, 120) : node.workflow_id);
        normalized.input_ports = structuredClone(declaration?.input_ports || metadataPorts(node.input_ports).map(({ id, ...port }) => port));
        normalized.output_ports = structuredClone(declaration?.output_ports || metadataPorts(node.output_ports).map(({ id, ...port }) => port));
      }
      return [normalized];
    });
    if (!normalizedNodes.some((node) => node.id === 'input' && node.type === 'input')) return false;
    if (!normalizedNodes.some((node) => node.type === 'output')) {
      normalizedNodes.push({ id: createWorkflowId('output'), type: 'output', name: 'Output', ...nextNodePosition() });
    }
    state.nodes = normalizedNodes;
    state.connections = (Array.isArray(saved?.connections) ? saved.connections : initialConnections).filter((connection) => {
      if (!connection || typeof connection.id !== 'string' || !['control', 'content', 'message', 'list-content', 'list-message'].includes(connection.type)) return false;
      const from = state.nodes.find((node) => node.id === connection.fromId);
      const to = state.nodes.find((node) => node.id === connection.toId);
      if (!from || !to || typeof connection.fromPortId !== 'string' || typeof connection.toPortId !== 'string') return false;
      const validFromPort = connection.type === 'control'
        ? (from.type === 'foreach'
          ? ['control-out', 'loop-out'].includes(connection.fromPortId)
          : from.type !== 'input' && from.type !== 'construct_message' && from.type !== 'construct_content' && from.type !== 'construct_list' && from.type !== 'llm' && from.type !== 'tool' && from.type !== 'tool_call' && from.type !== 'workflow'
          ? from.branches.some((branch) => branch.id === connection.fromPortId)
          : connection.fromPortId === 'control-out')
        : (from.type === 'input' && (from.workflowPorts || []).some((port) => port.id === connection.fromPortId && port.type === connection.type))
          || (from.type === 'construct_message' && connection.type === 'message' && connection.fromPortId === 'message-out')
          || (from.type === 'construct_content' && connection.type === 'content' && connection.fromPortId === 'content-out')
          || (['llm', 'tool'].includes(from.type) && connection.type === 'content' && connection.fromPortId === 'output')
          || (from.type === 'tool_call' && connection.type === 'content' && ['tool_call_id', 'result'].includes(connection.fromPortId))
          || (from.type === 'llm' && connection.type === 'content' && from.think === true && connection.fromPortId === 'reasoning')
          || (from.type === 'llm' && connection.type === 'list-content' && from.tool_calls === true && connection.fromPortId === 'tool_calls')
          || (from.type === 'construct_list' && connection.type === `list-${from.item_type}` && connection.fromPortId === 'list-out')
          || (from.type === 'foreach' && connection.type === from.item_type && connection.fromPortId === 'item-out')
          || (from.type === 'workflow' && (from.output_ports || []).some((port) => `workflow:${port.name}` === connection.fromPortId && port.type === connection.type));
      const validToPort = connection.type === 'control'
        ? to.type !== 'input' && (to.type === 'foreach'
          ? ['control-in', 'loop-in'].includes(connection.toPortId)
          : connection.toPortId === 'control-in')
        : (to.type === 'llm' && connection.type === 'message' && to.dataInputPorts.includes(connection.toPortId))
          || (to.type === 'construct_message' && connection.type === 'content' && connection.toPortId === 'content-in')
          || (to.type === 'construct_content' && connection.type === 'content' && to.dataInputPorts.includes(connection.toPortId))
          || (to.type === 'router' && connection.type === 'content' && connection.toPortId === 'content-in')
          || (to.type === 'tool' && connection.type === 'content' && to.parameters.includes(connection.toPortId))
          || (to.type === 'tool_call' && connection.type === 'content' && connection.toPortId === 'tool_call')
          || (to.type === 'construct_list' && connection.type === to.item_type && to.dataInputPorts.includes(connection.toPortId))
          || (to.type === 'foreach' && connection.type === `list-${to.item_type}` && connection.toPortId === 'list-in')
          || (to.type === 'output' && (
            (to.workflowPorts || []).some((port) => port.id === connection.toPortId && port.type === connection.type)
          ))
          || (to.type === 'workflow' && (to.input_ports || []).some((port) => `workflow:${port.name}` === connection.toPortId && port.type === connection.type));
      return validFromPort && validToPort;
    });
    state.selectedId = 'input';
    state.connectionDrag = null;
    return true;
  } catch (error) {
    console.warn('Workflow 数据读取失败', error);
    return false;
  }
}
