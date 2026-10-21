export const DATA_TYPES = new Set(['content', 'message', 'event', 'map-content', 'list-content', 'list-message', 'list-event']);

export const NODE_TYPES = new Set([
  'input',
  'output',
  'router',
  'construct_message',
  'construct_content',
  'construct_map_content',
  'construct_struct',
  'struct_get',
  'struct_update',
  'struct_to_json',
  'json_to_struct',
  'map_content_get',
  'deserialize_json',
  'split_event',
  'construct_event',
  'publish_event',
  'construct_list',
  'list_append',
  'foreach',
  'history',
  'llm',
  'local_tool',
  'remote_sync_tool',
  'remote_async_tool',
  'context_create',
  'context_read',
  'context_write',
  'session_create',
  'session_read',
  'session_write',
  'workflow',
]);

let idSequence = 0;

export function createWorkflowId(prefix) {
  idSequence += 1;
  return `${prefix}-${Date.now()}-${idSequence}`;
}

export function boundaryPorts(ports) {
  return (Array.isArray(ports) ? ports : []).flatMap((port) => {
    if (!port || typeof port.name !== 'string' || !DATA_TYPES.has(port.type)) return [];
    return [{ id: `workflow:${port.name}`, name: port.name.slice(0, 80), type: port.type }];
  });
}

function listTypeForItem(itemType) {
  return `list-${itemType}`;
}

function structsFor(node) {
  return node?._structs || [];
}

export function setNodeStructs(nodes, structs) {
  for (const node of nodes) node._structs = structs;
}

function structDefinition(node, id) {
  return structsFor(node).find((item) => item.id === id);
}

function structColor(node, type) {
  const match = /^(?:list-)?struct:(.+)$/.exec(type || '');
  return match ? structDefinition(node, match[1])?.color : null;
}

export function portsForNode(node) {
  if (node.type === 'input') {
    return [
      { id: 'control-out', direction: 'output', type: 'control', label: '下一步', title: '下一步', multiple: false },
      ...(node.workflowPorts || []).map((port) => ({ id: port.id, direction: 'output', type: port.type, label: port.name, title: port.name, multiple: true, contract: port.id })),
    ];
  }
  if (node.type === 'output') {
    return [
      { id: 'control-in', direction: 'input', type: 'control', label: '触发', title: '触发', multiple: false },
      ...(node.workflowPorts || []).map((port) => ({ id: port.id, direction: 'input', type: port.type, label: port.name, title: port.name, multiple: false, contract: port.id })),
    ];
  }
  if (node.type === 'router') {
    return [
      { id: 'control-in', direction: 'input', type: 'control', label: '触发', title: '触发', multiple: false },
      { id: 'content-in', direction: 'input', type: 'content', label: '输入', title: '输入内容', multiple: false },
      ...(node.branches || []).map((branch) => ({ id: branch.id, direction: 'output', type: 'control', label: branch.name, title: branch.name, multiple: false })),
      { id: 'branch$others', direction: 'output', type: 'control', label: '其它', title: '没有分支名称匹配时执行', multiple: false },
    ];
  }
  if (node.type === 'construct_message') {
    return [
      { id: 'control-in', direction: 'input', type: 'control', label: '触发', title: '触发', multiple: false },
      { id: 'content-in', direction: 'input', type: 'content', label: 'Content', title: 'Message content', multiple: false },
      ...(node.role_source === 'port'
        ? [{ id: 'role-in', direction: 'input', type: 'content', label: 'Role', title: 'Message role', multiple: false }]
        : []),
      { id: 'control-out', direction: 'output', type: 'control', label: '下一步', title: '下一步', multiple: false },
      { id: 'message-out', direction: 'output', type: 'message', label: 'Message', title: '构造后的 Message', multiple: true },
    ];
  }
  if (node.type === 'construct_content') {
    const inputPorts = (node.dataInputPorts || []).map((portId, index) => ({
      id: portId, direction: 'input', type: 'content', label: `内容 ${index}`, title: '构造内容输入', multiple: false,
    }));
    return [
      { id: 'control-in', direction: 'input', type: 'control', label: '触发', title: '触发', multiple: false },
      ...inputPorts,
      { id: 'control-out', direction: 'output', type: 'control', label: '下一步', title: '下一步', multiple: false },
      { id: 'content-out', direction: 'output', type: 'content', label: 'Content', title: '构造后的 Content', multiple: true },
    ];
  }
  if (node.type === 'construct_map_content') {
    const inputPorts = (node.mappings || []).filter((item) => item.value_source === 'port').map((item) => ({
      id: item.port_id, direction: 'input', type: 'content', label: item.key, title: `Map value: ${item.key}`, multiple: false,
    }));
    return [
      { id: 'control-in', direction: 'input', type: 'control', label: '触发', title: '构造 Map', multiple: false },
      ...inputPorts,
      { id: 'control-out', direction: 'output', type: 'control', label: '下一步', title: '下一步', multiple: false },
      { id: 'map-out', direction: 'output', type: 'map-content', label: 'Map', title: 'Map-Content', multiple: true },
    ];
  }
  if (node.type === 'construct_struct') {
    const definition = structDefinition(node, node.struct_id);
    if (!definition) return [
      { id: 'control-in', direction: 'input', type: 'control', label: '触发', title: '构造 Struct', multiple: false },
      { id: 'control-out', direction: 'output', type: 'control', label: '下一步', title: '下一步', multiple: false },
    ];
    return [
      { id: 'control-in', direction: 'input', type: 'control', label: '触发', title: '构造 Struct', multiple: false },
      ...(definition?.fields || []).map((field) => ({ id: field.name, direction: 'input', type: field.type, color: structColor(node, field.type), label: field.name, title: `${field.name}: ${field.type}${field.required ? ' (必需)' : ' (可选)'}`, multiple: false })),
      { id: 'control-out', direction: 'output', type: 'control', label: '下一步', title: '下一步', multiple: false },
      { id: 'struct-out', direction: 'output', type: `struct:${node.struct_id}`, color: structColor(node, `struct:${node.struct_id}`), label: definition?.name || node.struct_id, title: `struct:${node.struct_id}`, multiple: true },
    ];
  }
  if (node.type === 'struct_get') {
    const definition = structDefinition(node, node.struct_id);
    if (!definition) return [
      { id: 'control-in', direction: 'input', type: 'control', label: '触发', title: '读取字段', multiple: false },
      { id: 'control-out', direction: 'output', type: 'control', label: '下一步', title: '下一步', multiple: false },
    ];
    const field = definition?.fields.find((item) => item.name === node.field);
    return [
      { id: 'control-in', direction: 'input', type: 'control', label: '触发', title: '读取字段', multiple: false },
      { id: 'struct-in', direction: 'input', type: `struct:${node.struct_id}`, color: structColor(node, `struct:${node.struct_id}`), label: definition?.name || node.struct_id, title: `struct:${node.struct_id}`, multiple: false },
      ...(node.has_fallback ? [{ id: 'fallback-in', direction: 'input', type: field?.type || 'content', color: structColor(node, field?.type), label: 'Fallback', title: '字段缺失时的替代值', multiple: false }] : []),
      { id: 'control-out', direction: 'output', type: 'control', label: '下一步', title: '下一步', multiple: false },
      ...(field ? [{ id: 'value-out', direction: 'output', type: field.type, color: structColor(node, field.type), label: node.field, title: `${node.field}: ${field.type}`, multiple: true }] : []),
    ];
  }
  if (node.type === 'struct_update') {
    const definition = structDefinition(node, node.struct_id);
    if (!definition) return [
      { id: 'control-in', direction: 'input', type: 'control', label: '触发', title: '更新 Struct', multiple: false },
      { id: 'control-out', direction: 'output', type: 'control', label: '下一步', title: '下一步', multiple: false },
    ];
    const fields = new Map((definition?.fields || []).map((field) => [field.name, field]));
    return [
      { id: 'control-in', direction: 'input', type: 'control', label: '触发', title: '更新 Struct', multiple: false },
      { id: 'struct-in', direction: 'input', type: `struct:${node.struct_id}`, color: structColor(node, `struct:${node.struct_id}`), label: '原值', title: `struct:${node.struct_id}`, multiple: false },
      ...(node.updates || []).flatMap((name) => fields.has(name) ? [{ id: name, direction: 'input', type: fields.get(name).type, color: structColor(node, fields.get(name).type), label: name, title: `替换字段 ${name}`, multiple: false }] : []),
      { id: 'control-out', direction: 'output', type: 'control', label: '下一步', title: '下一步', multiple: false },
      { id: 'struct-out', direction: 'output', type: `struct:${node.struct_id}`, color: structColor(node, `struct:${node.struct_id}`), label: definition?.name || node.struct_id, title: `struct:${node.struct_id}`, multiple: true },
    ];
  }
  if (node.type === 'struct_to_json' || node.type === 'json_to_struct') {
    const toJson = node.type === 'struct_to_json';
    const valueType = node.value_type || 'struct:';
    if (!structDefinition(node, valueType.replace(/^list-/, '').slice('struct:'.length))) return [
      { id: 'control-in', direction: 'input', type: 'control', label: '触发', title: toJson ? '转换为 JSON' : '解析 JSON', multiple: false },
      { id: 'control-out', direction: 'output', type: 'control', label: '下一步', title: '下一步', multiple: false },
    ];
    return [
      { id: 'control-in', direction: 'input', type: 'control', label: '触发', title: toJson ? '转换为 JSON' : '解析 JSON', multiple: false },
      { id: toJson ? 'value-in' : 'content-in', direction: 'input', type: toJson ? valueType : 'content', color: structColor(node, valueType), label: toJson ? valueType : 'JSON', title: toJson ? valueType : 'JSON content', multiple: false },
      { id: 'control-out', direction: 'output', type: 'control', label: '下一步', title: '下一步', multiple: false },
      { id: toJson ? 'content-out' : 'value-out', direction: 'output', type: toJson ? 'content' : valueType, color: structColor(node, valueType), label: toJson ? 'JSON' : valueType, title: toJson ? 'JSON content' : valueType, multiple: true },
    ];
  }
  if (node.type === 'map_content_get') {
    return [
      { id: 'control-in', direction: 'input', type: 'control', label: '触发', title: '查询 Map', multiple: false },
      { id: 'map-in', direction: 'input', type: 'map-content', label: 'Map', title: 'Map-Content', multiple: false },
      { id: 'key-in', direction: 'input', type: 'content', label: 'Key', title: '查找键', multiple: false },
      { id: 'control-out', direction: 'output', type: 'control', label: '下一步', title: '下一步', multiple: false },
      { id: 'content-out', direction: 'output', type: 'content', label: 'Content', title: '查找到的 Content', multiple: true },
    ];
  }
  if (node.type === 'split_event') {
    return [
      { id: 'control-in', direction: 'input', type: 'control', label: '触发', title: '触发拆分', multiple: false },
      { id: 'event-in', direction: 'input', type: 'event', label: 'Event', title: '待拆分的事件', multiple: false },
      { id: 'control-out', direction: 'output', type: 'control', label: '下一步', title: '下一步', multiple: false },
      { id: 'type-out', direction: 'output', type: 'content', label: 'Type', title: '事件类型', multiple: true },
      { id: 'payload-out', direction: 'output', type: 'content', label: 'Payload', title: '事件 Payload 对象', multiple: true },
    ];
  }
  if (node.type === 'publish_event') {
    return [
      { id: 'control-in', direction: 'input', type: 'control', label: '触发', title: '发布 Event', multiple: false },
      { id: 'event-in', direction: 'input', type: 'event', label: 'Event', title: '待发布的事件', multiple: false },
      { id: 'control-out', direction: 'output', type: 'control', label: '下一步', title: '发布后继续', multiple: false },
    ];
  }
  if (node.type === 'construct_event') {
    return [
      { id: 'control-in', direction: 'input', type: 'control', label: '触发', title: '构造 Event', multiple: false },
      { id: 'payload-in', direction: 'input', type: 'content', label: 'Payload JSON', title: 'JSON 对象字符串', multiple: false },
      { id: 'control-out', direction: 'output', type: 'control', label: '下一步', title: '下一步', multiple: false },
      { id: 'event-out', direction: 'output', type: 'event', label: 'Event', title: '构造后的 Event', multiple: true },
    ];
  }
  if (node.type === 'deserialize_json') {
    return [
      { id: 'control-in', direction: 'input', type: 'control', label: '触发', title: '触发 JSON 反序列化', multiple: false },
      { id: 'content-in', direction: 'input', type: 'content', label: 'JSON', title: 'JSON 对象字符串', multiple: false },
      { id: 'control-out', direction: 'output', type: 'control', label: '下一步', title: '下一步', multiple: false },
      ...node.outputs.map((output) => ({ id: output.key, direction: 'output', type: output.type, label: output.key, title: output.type, multiple: true })),
    ];
  }
  if (node.type === 'construct_list') {
    const itemPorts = (node.dataInputPorts || []).map((portId, index) => ({
      id: portId,
      direction: 'input',
      type: node.item_type,
      label: `${node.item_type} ${index}`,
      title: `列表初始值 ${index}`,
      multiple: false,
    }));
    return [
      { id: 'control-in', direction: 'input', type: 'control', label: '触发', title: '触发', multiple: false },
      ...itemPorts,
      { id: 'control-out', direction: 'output', type: 'control', label: '下一步', title: '下一步', multiple: false },
      { id: 'list-out', direction: 'output', type: listTypeForItem(node.item_type), label: '列表', title: listTypeForItem(node.item_type), multiple: true },
    ];
  }
  if (node.type === 'list_append') {
    return [
      { id: 'control-in', direction: 'input', type: 'control', label: '触发', title: '触发', multiple: false },
      { id: 'list-in', direction: 'input', type: listTypeForItem(node.item_type), label: '列表', title: listTypeForItem(node.item_type), multiple: false },
      { id: 'item-in', direction: 'input', type: node.item_type, label: '追加项', title: node.item_type, multiple: false },
      { id: 'control-out', direction: 'output', type: 'control', label: '下一步', title: '下一步', multiple: false },
      { id: 'list-out', direction: 'output', type: listTypeForItem(node.item_type), label: '新列表', title: listTypeForItem(node.item_type), multiple: true },
    ];
  }
  if (node.type === 'foreach') {
    return [
      { id: 'control-in', direction: 'input', type: 'control', label: '触发', title: '触发遍历', multiple: false },
      { id: 'loop-in', direction: 'input', type: 'control', label: '循环体结束', title: '循环体完成后返回', multiple: false },
      { id: 'list-in', direction: 'input', type: listTypeForItem(node.item_type), label: '列表', title: listTypeForItem(node.item_type), multiple: false },
      { id: 'control-out', direction: 'output', type: 'control', label: '下一步', title: '列表遍历完成后继续', multiple: false },
      { id: 'loop-out', direction: 'output', type: 'control', label: '循环体开始', title: '执行当前项的循环体', multiple: false },
      { id: 'item-out', direction: 'output', type: node.item_type, label: '当前项', title: `当前 ${node.item_type}`, multiple: true },
    ];
  }
  if (node.type === 'history') {
    return [
      { id: 'control-in', direction: 'input', type: 'control', label: '触发', title: '触发查询', multiple: false },
      { id: 'control-out', direction: 'output', type: 'control', label: '下一步', title: '下一步', multiple: false },
      { id: 'events', direction: 'output', type: 'list-event', label: '事件', title: '最近的事件列表', multiple: true },
    ];
  }
  if (node.type === 'context_create' || node.type === 'session_create') {
    const isSession = node.type === 'session_create';
    const idPort = isSession ? 'session-id' : 'context-id';
    const label = isSession ? 'Session' : 'Context';
    return [
      { id: 'control-in', direction: 'input', type: 'control', label: '触发', title: `创建 ${label}`, multiple: false },
      { id: 'initial-value', direction: 'input', type: node.value_type, label: '初始值', title: node.value_type, multiple: false },
      { id: 'control-out', direction: 'output', type: 'control', label: '下一步', title: '下一步', multiple: false },
      { id: idPort, direction: 'output', type: 'content', label: `${label} ID`, title: `${label} ID`, multiple: true },
    ];
  }
  if (node.type === 'context_read' || node.type === 'session_read') {
    const isSession = node.type === 'session_read';
    const idPort = isSession ? 'session-id' : 'context-id';
    const label = isSession ? 'Session' : 'Context';
    const ports = [
      { id: 'control-in', direction: 'input', type: 'control', label: '触发', title: `读取 ${label}`, multiple: false },
      { id: 'control-out', direction: 'output', type: 'control', label: '下一步', title: '下一步', multiple: false },
      { id: 'value-out', direction: 'output', type: node.value_type, label: '值', title: node.value_type, multiple: true },
    ];
    if (node.type === 'session_read' || (node.context_id_source || 'port') === 'port') {
      ports.splice(1, 0, { id: idPort, direction: 'input', type: 'content', label: `${label} ID`, title: `${label} ID`, multiple: false });
    }
    return ports;
  }
  if (node.type === 'context_write' || node.type === 'session_write') {
    const isSession = node.type === 'session_write';
    const idPort = isSession ? 'session-id' : 'context-id';
    const label = isSession ? 'Session' : 'Context';
    const ports = [
      { id: 'control-in', direction: 'input', type: 'control', label: '触发', title: `修改 ${label}`, multiple: false },
      { id: 'value-in', direction: 'input', type: node.value_type, label: '新值', title: node.value_type, multiple: false },
      { id: 'control-out', direction: 'output', type: 'control', label: '下一步', title: '下一步', multiple: false },
      { id: idPort, direction: 'output', type: 'content', label: `${label} ID`, title: `${label} ID`, multiple: true },
      { id: 'value-out', direction: 'output', type: node.value_type, label: '新值', title: node.value_type, multiple: true },
    ];
    if (node.type === 'session_write' || (node.context_id_source || 'port') === 'port') {
      ports.splice(1, 0, { id: idPort, direction: 'input', type: 'content', label: `${label} ID`, title: `${label} ID`, multiple: false });
    }
    return ports;
  }
  if (['local_tool', 'remote_sync_tool', 'remote_async_tool'].includes(node.type)) {
    const isRemote = node.type !== 'local_tool';
    const parameterPorts = (node.parameters || []).map((parameter) => ({
      id: isRemote ? parameter.name : parameter,
      direction: 'input',
      type: isRemote ? parameter.type : 'content',
      label: isRemote ? parameter.name : parameter,
      title: `工具参数: ${isRemote ? parameter.name : parameter}`,
      multiple: false,
    }));
    const resultPorts = node.type === 'remote_sync_tool'
      ? (node.outputs || []).map((output) => ({ id: output.name, direction: 'output', type: output.type, label: output.name, title: `工具输出: ${output.name}`, multiple: true }))
      : [{
        id: node.type === 'remote_async_tool' ? 'task_id' : 'output',
        direction: 'output',
        type: 'content',
        label: node.type === 'remote_async_tool' ? 'Task ID' : '结果',
        title: node.type === 'remote_async_tool' ? '已发布任务 ID' : '工具执行结果',
        multiple: true,
      }];
    return [
      { id: 'control-in', direction: 'input', type: 'control', label: '触发', title: '触发', multiple: false },
      ...parameterPorts,
      { id: 'control-out', direction: 'output', type: 'control', label: '下一步', title: '下一步', multiple: false },
      ...resultPorts,
    ];
  }
  if (node.type === 'workflow') {
    return [
      { id: 'control-in', direction: 'input', type: 'control', label: '触发', title: '调用 Workflow', multiple: false },
      ...(node.input_ports || []).map((port) => ({ id: `workflow:${port.name}`, direction: 'input', type: port.type, label: port.name, title: port.name, multiple: false })),
      { id: 'control-out', direction: 'output', type: 'control', label: '下一步', title: 'Workflow 完成后继续', multiple: false },
      ...(node.output_ports || []).map((port) => ({ id: `workflow:${port.name}`, direction: 'output', type: port.type, label: port.name, title: port.name, multiple: true })),
    ];
  }
  const ports = [
    { id: 'control-in', direction: 'input', type: 'control', label: '触发', title: '触发', multiple: false },
    { id: 'messages-in', direction: 'input', type: 'list-message', label: 'Messages', title: 'Message 列表', multiple: false },
    { id: 'control-out', direction: 'output', type: 'control', label: '下一步', title: '下一步', multiple: false },
    { id: 'output', direction: 'output', type: 'content', label: '输出', title: '模型输出', multiple: true },
  ];
  if (node.think === true) ports.push({ id: 'reasoning', direction: 'output', type: 'content', label: '思考', title: '推理过程', multiple: true });
  if (node.tool_calls === true) ports.push({ id: 'tool_calls', direction: 'output', type: 'list-content', label: 'Tool Calls', title: 'OpenAI 格式的 tool_calls JSON 数组', multiple: true });
  return ports;
}

function nextNodePosition(nodes, viewport) {
  const left = Math.max(12, viewport?.left ?? 52);
  const top = Math.max(12, viewport?.top ?? 72);
  const width = Math.max(210, viewport?.width ?? 900);
  const height = Math.max(125, viewport?.height ?? 600);
  const columns = Math.max(1, Math.floor((width - 24) / 258));
  const rows = Math.max(1, Math.floor((height - 24) / 150));
  const positions = [];
  for (let row = 0; row < rows; row += 1) {
    for (let column = 0; column < columns; column += 1) {
      positions.push({ x: left + column * 258, y: top + row * 150 });
    }
  }
  const available = positions.find((position) => nodes.every((node) => Math.abs(node.x - position.x) >= 210 || Math.abs(node.y - position.y) >= 125));
  if (available) return available;
  const stackIndex = nodes.filter((node) => node.x >= left && node.x < left + width && node.y >= top && node.y < top + height).length;
  const maxOffsetX = Math.max(0, width - 202);
  const maxOffsetY = Math.max(0, height - 132);
  const offsetSteps = Math.max(1, Math.floor(Math.min(maxOffsetX, maxOffsetY) / 18) + 1);
  const stackLayer = Math.floor(stackIndex / offsetSteps);
  const stackOffset = (stackIndex % offsetSteps) * 18;
  const alternateX = Math.max(0, width - 202 - stackOffset);
  const alternateY = Math.max(0, height - 132 - stackOffset);
  return {
    x: left + (stackLayer % 2 === 0 ? stackOffset : alternateX),
    y: top + (stackLayer % 2 === 0 ? stackOffset : alternateY),
  };
}

export function createNode(type, nodes, configuration = null, viewport = null) {
  if (!NODE_TYPES.has(type) || type === 'input') return null;
  const number = nodes.filter((node) => node.type === type).length + 1;
  const position = nextNodePosition(nodes, viewport);
  if (type === 'router') return { id: createWorkflowId('router'), type, name: `Router ${number}`, branches: [{ id: createWorkflowId('branch'), name: '分支 1' }, { id: createWorkflowId('branch'), name: '分支 2' }], ...position };
  if (type === 'output') return { id: createWorkflowId('output'), type, name: `Output ${number}`, workflowPorts: boundaryPorts(configuration?.output_ports), ...position };
  if (type === 'construct_message') return { id: createWorkflowId('construct-message'), type, name: `构造 Message ${number}`, role_source: 'fixed', role: 'user', ...position };
  if (type === 'construct_content') return { id: createWorkflowId('construct-content'), type, name: `构造 Content ${number}`, append_items: [{ type: 'fixed', value: '' }], dataInputPorts: [], ...position };
  if (type === 'construct_map_content') return { id: createWorkflowId('construct-map-content'), type, name: `构造 Map ${number}`, mappings: [{ key: 'key1', value: '' }], dataInputPorts: [], ...position };
  if (['construct_struct', 'struct_get', 'struct_update'].includes(type)) {
    const prefix = type.replaceAll('_', '-');
    const label = type === 'construct_struct' ? '构造 Struct' : type === 'struct_get' ? '读取 Struct 字段' : '更新 Struct';
    const node = { id: createWorkflowId(prefix), type, name: `${label} ${number}`, struct_id: '', ...position };
    if (type === 'construct_struct') node.dataInputPorts = [];
    if (type === 'struct_get') Object.assign(node, { field: '', missing: 'error', has_fallback: false, dataInputPorts: [] });
    if (type === 'struct_update') Object.assign(node, { updates: [], remove_fields: [], dataInputPorts: [] });
    return node;
  }
  if (type === 'struct_to_json' || type === 'json_to_struct') {
    return { id: createWorkflowId(type.replaceAll('_', '-')), type, name: type === 'struct_to_json' ? `Struct 转 JSON ${number}` : `JSON 转 Struct ${number}`, value_type: '', ...position };
  }
  if (type === 'map_content_get') return { id: createWorkflowId('map-content-get'), type, name: `Map 查找 ${number}`, ...position };
  if (type === 'deserialize_json') return { id: createWorkflowId('deserialize-json'), type, name: `反序列化 JSON ${number}`, outputs: [{ key: 'value', type: 'content' }], ...position };
  if (type === 'split_event') return { id: createWorkflowId('split-event'), type, name: `拆分 Event ${number}`, ...position };
  if (type === 'publish_event') return { id: createWorkflowId('publish-event'), type, name: `发布 Event ${number}`, ...position };
  if (type === 'construct_event') return { id: createWorkflowId('construct-event'), type, name: `构造 Event ${number}`, event_type: 'event_type', ...position };
  if (type === 'construct_list') return { id: createWorkflowId('construct-list'), type, name: `构造列表 ${number}`, item_type: 'content', initial_value_count: 1, dataInputPorts: ['content-in-0'], ...position };
  if (type === 'list_append') return { id: createWorkflowId('list-append'), type, name: `List 追加 ${number}`, item_type: 'content', position: 'end', ...position };
  if (type === 'foreach') return { id: createWorkflowId('foreach'), type, name: `遍历列表 ${number}`, item_type: 'content', ...position };
  if (type === 'history') return { id: createWorkflowId('history'), type, name: `召回 History ${number}`, event_types: ['terminal', 'response'], limit: 10, ...position };
  if (type === 'context_create') return { id: createWorkflowId('context-create'), type, name: `创建 Context ${number}`, value_type: 'content', ...position };
  if (type === 'context_read') return { id: createWorkflowId('context-read'), type, name: `读取 Context ${number}`, value_type: 'content', context_id_source: 'port', ...position };
  if (type === 'context_write') return { id: createWorkflowId('context-write'), type, name: `修改 Context ${number}`, value_type: 'content', context_id_source: 'port', ...position };
  if (type === 'session_create') return { id: createWorkflowId('session-create'), type, name: `创建 Session ${number}`, value_type: 'content', ...position };
  if (type === 'session_read') return { id: createWorkflowId('session-read'), type, name: `读取 Session ${number}`, value_type: 'content', ...position };
  if (type === 'session_write') return { id: createWorkflowId('session-write'), type, name: `修改 Session ${number}`, value_type: 'content', ...position };
  if (type === 'llm') return { id: createWorkflowId('llm'), type, name: `LLM ${number}`, model: '', tools: [], think: false, tool_calls: false, ...position };
  if (type === 'local_tool') return { id: createWorkflowId('local-tool'), type, name: `Local Tool ${number}`, tool: '', parameters: [], ...position };
  if (type === 'remote_sync_tool') return { id: createWorkflowId('remote-sync-tool'), type, name: `Remote Sync Tool ${number}`, tool: '', parameters: [], outputs: [], timeout_ms: 10000, ...position };
  if (type === 'remote_async_tool') return { id: createWorkflowId('remote-async-tool'), type, name: `Remote Async Tool ${number}`, tool: '', parameters: [], timeout_ms: 600000, callback: null, ...position };
  if (type === 'workflow' && configuration) {
    return {
      id: createWorkflowId('workflow'),
      type,
      name: configuration.name || `Workflow ${number}`,
      workflow_name: configuration.name,
      input_ports: structuredClone(configuration.input_ports || []),
      output_ports: structuredClone(configuration.output_ports || []),
      ...position,
    };
  }
  return null;
}
