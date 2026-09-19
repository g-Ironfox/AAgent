const NODE_WIDTH = 190;
const NODE_HEIGHT = 86;
const PADDING = 56;

const TYPE_COLORS = {
  input: '#13775a',
  output: '#785d9b',
  router: '#c18413',
  construct_message: '#b75b18',
  construct_content: '#2f6f8f',
  split_event: '#147d78',
  construct_list: '#176f73',
  list_append: '#27705b',
  foreach: '#9a5a24',
  history: '#396a87',
  llm: '#356e9b',
  local_tool: '#13775a',
  remote_sync_tool: '#a94f36',
  remote_async_tool: '#b47a22',
  context_create: '#326b4b',
  context_read: '#376c78',
  context_write: '#8a5b2d',
  workflow: '#785d9b',
};

const CONNECTION_COLORS = {
  control: '#5f7168',
  content: '#356e9b',
  message: '#b75b18',
  event: '#147d78',
  'list-content': '#d12f72',
  'list-message': '#7a3e88',
  'event-list': '#147d78',
};

function escapeXml(value) {
  return String(value ?? '').replace(/[&<>"']/g, (character) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&apos;',
  })[character]);
}

function safeCoordinate(value) {
  return Number.isFinite(Number(value)) ? Number(value) : 0;
}

function nodeArguments(node) {
  return node?.arguments && typeof node.arguments === 'object' ? node.arguments : {};
}

function workflowPortIds(ports) {
  return (Array.isArray(ports) ? ports : []).map((port) => `workflow:${port.name}`);
}

function contractPortIds(node, direction, workflow) {
  const args = nodeArguments(node);
  if (node.type === 'input') return direction === 'output' ? ['control-out', ...workflowPortIds(workflow?.input_ports)] : [];
  if (node.type === 'output') return direction === 'input' ? ['control-in', ...workflowPortIds(workflow?.output_ports)] : [];
  if (node.type === 'router') return direction === 'input'
    ? ['control-in', 'content-in']
    : (Array.isArray(args.branches) ? args.branches.map((branch) => branch.id) : []);
  if (node.type === 'construct_message') return direction === 'input' ? ['control-in', 'content-in'] : ['control-out', 'message-out'];
  if (node.type === 'construct_content') {
    const inputs = (Array.isArray(args.append_items) ? args.append_items : [])
      .filter((item) => item?.type === 'port')
      .map((item) => item.port_id);
    return direction === 'input' ? ['control-in', ...inputs] : ['control-out', 'content-out'];
  }
  if (node.type === 'split_event') return direction === 'input' ? ['control-in', 'event-in'] : ['control-out', 'type-out', 'payload-out'];
  if (node.type === 'construct_list') {
    const count = Number.isInteger(args.initial_value_count) ? args.initial_value_count : 1;
    const inputs = Array.from({ length: count }, (_, index) => `${args.item_type || 'content'}-in-${index}`);
    return direction === 'input' ? ['control-in', ...inputs] : ['control-out', 'list-out'];
  }
  if (node.type === 'list_append') return direction === 'input' ? ['control-in', 'list-in', 'item-in'] : ['control-out', 'list-out'];
  if (node.type === 'foreach') return direction === 'input' ? ['control-in', 'loop-in', 'list-in'] : ['control-out', 'loop-out', 'item-out'];
  if (node.type === 'history') return direction === 'input' ? ['control-in'] : ['control-out', 'events'];
  if (node.type === 'context_create') return direction === 'input' ? ['control-in', 'initial-value'] : ['control-out', 'context-id'];
  if (node.type === 'context_read') return direction === 'input' ? ['control-in', 'context-id'] : ['control-out', 'value-out'];
  if (node.type === 'context_write') return direction === 'input' ? ['control-in', 'context-id', 'value-in'] : ['control-out', 'context-id', 'value-out'];
  if (['local_tool', 'remote_sync_tool', 'remote_async_tool'].includes(node.type)) {
    const parameters = (Array.isArray(args.parameters) ? args.parameters : []).map((parameter) => (
      typeof parameter === 'string' ? parameter : parameter.name
    ));
    if (direction === 'input') return ['control-in', ...parameters];
    if (node.type === 'remote_sync_tool') return ['control-out', ...(Array.isArray(args.outputs) ? args.outputs.map((output) => output.name) : [])];
    return ['control-out', node.type === 'remote_async_tool' ? 'task_id' : 'output'];
  }
  if (node.type === 'workflow') {
    const reference = (Array.isArray(workflow?.workflow_nodes) ? workflow.workflow_nodes : [])
      .find((item) => item.name === args.workflow_name);
    return direction === 'input'
      ? ['control-in', ...workflowPortIds(reference?.input_ports)]
      : ['control-out', ...workflowPortIds(reference?.output_ports)];
  }
  if (node.type === 'llm') {
    return direction === 'input'
      ? ['control-in', 'messages-in']
      : ['control-out', 'output', ...(args.think === true ? ['reasoning'] : []), ...(args.tool_calls === true ? ['tool_calls'] : [])];
  }
  return [];
}

function endpointRows(connections, node, direction, workflow) {
  const nodeKey = direction === 'output' ? 'fromId' : 'toId';
  const portKey = direction === 'output' ? 'fromPortId' : 'toPortId';
  const connected = [...new Set(connections.filter((item) => item[nodeKey] === node.id).map((item) => item[portKey]))];
  const order = contractPortIds(node, direction, workflow);
  return connected.sort((left, right) => {
    const leftIndex = order.indexOf(left);
    const rightIndex = order.indexOf(right);
    if (leftIndex < 0) return rightIndex < 0 ? 0 : 1;
    if (rightIndex < 0) return -1;
    return leftIndex - rightIndex;
  });
}

function endpointPosition(node, portId, direction, connections, workflow) {
  const ports = endpointRows(connections, node, direction, workflow);
  const row = Math.max(0, ports.indexOf(portId));
  return {
    x: node.renderX + (direction === 'output' ? NODE_WIDTH : 0),
    y: node.renderY + 52 + row * 18,
  };
}

function connectionPath(start, end) {
  const curve = Math.max(42, Math.abs(end.x - start.x) * 0.45);
  return `M ${start.x} ${start.y} C ${start.x + curve} ${start.y}, ${end.x - curve} ${end.y}, ${end.x} ${end.y}`;
}

function nodeHeight(node, connections, workflow) {
  return Math.max(
    NODE_HEIGHT,
    64 + Math.max(endpointRows(connections, node, 'input', workflow).length, endpointRows(connections, node, 'output', workflow).length) * 18,
  );
}

export function workflowCanvasSvg(workflow) {
  const sourceNodes = Array.isArray(workflow?.nodes) ? workflow.nodes : [];
  const connections = Array.isArray(workflow?.connections) ? workflow.connections : [];
  const minX = Math.min(0, ...sourceNodes.map((node) => safeCoordinate(node.x)));
  const minY = Math.min(0, ...sourceNodes.map((node) => safeCoordinate(node.y)));
  const nodes = sourceNodes.map((node) => ({
    ...node,
    renderX: safeCoordinate(node.x) - minX + PADDING,
    renderY: safeCoordinate(node.y) - minY + PADDING + 54,
  }));
  const nodeById = new Map(nodes.map((node) => [node.id, node]));
  const width = Math.max(720, ...nodes.map((node) => node.renderX + NODE_WIDTH + PADDING));
  const height = Math.max(360, ...nodes.map((node) => node.renderY + nodeHeight(node, connections, workflow) + PADDING));

  const paths = connections.flatMap((connection) => {
    const source = nodeById.get(connection.fromId);
    const target = nodeById.get(connection.toId);
    if (!source || !target) return [];
    const start = endpointPosition(source, connection.fromPortId, 'output', connections, workflow);
    const end = endpointPosition(target, connection.toPortId, 'input', connections, workflow);
    const color = CONNECTION_COLORS[connection.type] || CONNECTION_COLORS.control;
    const dash = connection.type === 'control' ? '' : ' stroke-dasharray="6 5"';
    return `<path d="${connectionPath(start, end)}" fill="none" stroke="${color}" stroke-width="2"${dash}/>`;
  }).join('');

  const cards = nodes.map((node) => {
    const heightValue = nodeHeight(node, connections, workflow);
    const inputPorts = endpointRows(connections, node, 'input', workflow);
    const outputPorts = endpointRows(connections, node, 'output', workflow);
    const ports = [
      ...inputPorts.map((portId, index) => `<circle cx="0" cy="${52 + index * 18}" r="5"/><text x="10" y="${56 + index * 18}">${escapeXml(portId)}</text>`),
      ...outputPorts.map((portId, index) => `<circle cx="${NODE_WIDTH}" cy="${52 + index * 18}" r="5"/><text x="${NODE_WIDTH - 10}" y="${56 + index * 18}" text-anchor="end">${escapeXml(portId)}</text>`),
    ].join('');
    return `<g transform="translate(${node.renderX} ${node.renderY})">
      <rect width="${NODE_WIDTH}" height="${heightValue}" fill="#fff" stroke="#cbd2cd"/>
      <rect width="${NODE_WIDTH}" height="4" fill="${TYPE_COLORS[node.type] || '#17201d'}"/>
      <line x1="0" y1="40" x2="${NODE_WIDTH}" y2="40" stroke="#d8ddd9"/>
      <text x="12" y="24" class="node-name">${escapeXml(node.name || '未命名节点')}</text>
      <text x="12" y="36" class="node-type">${escapeXml(String(node.type || 'node').toUpperCase())}</text>
      <g class="ports" fill="${TYPE_COLORS[node.type] || '#17201d'}">${ports}</g>
    </g>`;
  }).join('');

  return `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeXml(workflow?.name || 'Workflow')} 完整画布">
    <defs><pattern id="grid" width="24" height="24" patternUnits="userSpaceOnUse"><path d="M 24 0 L 0 0 0 24" fill="none" stroke="#dfe4df" stroke-width="1"/></pattern></defs>
    <style>text{font-family:"Microsoft YaHei",sans-serif;fill:#17201d}.title{font-size:20px;font-weight:700}.meta,.node-type{font-family:Consolas,monospace;fill:#68736e}.meta{font-size:10px}.node-name{font-size:11px;font-weight:700}.node-type{font-size:8px}.ports text{font-family:Consolas,"Microsoft YaHei",sans-serif;font-size:8px;fill:#68736e}.ports circle{stroke:#fff;stroke-width:2}</style>
    <rect width="${width}" height="${height}" fill="#f5f6f3"/><rect width="${width}" height="${height}" fill="url(#grid)"/>
    <g class="canvas-heading"><text x="${PADDING}" y="32" class="title">${escapeXml(workflow?.name || 'Workflow')}</text>
    <text x="${PADDING}" y="48" class="meta">${nodes.length} NODES / ${connections.length} CONNECTIONS / VERSION ${escapeXml(workflow?.version || 1)}</text></g>
    <g>${paths}</g><g>${cards}</g>
  </svg>`;
}

export function workflowCanvasFilename(name) {
  const safeName = String(name || 'workflow').replace(/[<>:"/\\|?*]+/g, '-').replace(/\s+/g, '-');
  return `${safeName}-${new Date().toISOString().slice(0, 10)}-canvas.svg`;
}