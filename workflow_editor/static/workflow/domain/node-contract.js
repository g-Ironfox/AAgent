export const DATA_TYPES = new Set(['content', 'message', 'list-content', 'list-message']);

export const NODE_TYPES = new Set([
  'input',
  'output',
  'router',
  'construct_message',
  'construct_content',
  'construct_list',
  'foreach',
  'history',
  'llm',
  'local_tool',
  'remote_sync_tool',
  'remote_async_tool',
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
      ...node.branches.map((branch) => ({ id: branch.id, direction: 'output', type: 'control', label: branch.name, title: branch.name, multiple: false })),
    ];
  }
  if (node.type === 'construct_message') {
    return [
      { id: 'control-in', direction: 'input', type: 'control', label: '触发', title: '触发', multiple: false },
      { id: 'content-in', direction: 'input', type: 'content', label: 'Content', title: 'Message content', multiple: false },
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
      { id: 'list-out', direction: 'output', type: `list-${node.item_type}`, label: '列表', title: `list-${node.item_type}`, multiple: true },
    ];
  }
  if (node.type === 'foreach') {
    return [
      { id: 'control-in', direction: 'input', type: 'control', label: '触发', title: '触发遍历', multiple: false },
      { id: 'loop-in', direction: 'input', type: 'control', label: '循环体结束', title: '循环体完成后返回', multiple: false },
      { id: 'list-in', direction: 'input', type: `list-${node.item_type}`, label: '列表', title: `list-${node.item_type}`, multiple: false },
      { id: 'control-out', direction: 'output', type: 'control', label: '下一步', title: '列表遍历完成后继续', multiple: false },
      { id: 'loop-out', direction: 'output', type: 'control', label: '循环体开始', title: '执行当前项的循环体', multiple: false },
      { id: 'item-out', direction: 'output', type: node.item_type, label: '当前项', title: `当前 ${node.item_type}`, multiple: true },
    ];
  }
  if (node.type === 'history') {
    return [
      { id: 'control-in', direction: 'input', type: 'control', label: '触发', title: '触发查询', multiple: false },
      { id: 'control-out', direction: 'output', type: 'control', label: '下一步', title: '下一步', multiple: false },
      { id: 'events', direction: 'output', type: 'list-content', label: '事件', title: '最近的事件 JSON 列表', multiple: true },
    ];
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
  const inputPorts = (node.dataInputPorts || ['message-in-0']).map((portId, index) => ({
    id: portId,
    direction: 'input',
    type: 'message',
    label: `Message ${index}`,
    title: `Message ${index}`,
    multiple: false,
  }));
  const ports = [
    { id: 'control-in', direction: 'input', type: 'control', label: '触发', title: '触发', multiple: false },
    ...inputPorts,
    { id: 'control-out', direction: 'output', type: 'control', label: '下一步', title: '下一步', multiple: false },
    { id: 'output', direction: 'output', type: 'content', label: '输出', title: '模型输出', multiple: true },
  ];
  if (node.think === true) ports.push({ id: 'reasoning', direction: 'output', type: 'content', label: '思考', title: '推理过程', multiple: true });
  if (node.tool_calls === true) ports.push({ id: 'tool_calls', direction: 'output', type: 'list-content', label: 'Tool Calls', title: 'OpenAI 格式的 tool_calls JSON 数组', multiple: true });
  return ports;
}

function nextNodePosition(nodes) {
  const positions = [];
  for (let row = 0; row < 4; row += 1) {
    for (let column = 0; column < 3; column += 1) {
      positions.push({ x: 52 + column * 258, y: 72 + row * 150 });
    }
  }
  const available = positions.find((position) => nodes.every((node) => Math.abs(node.x - position.x) >= 210 || Math.abs(node.y - position.y) >= 125));
  if (available) return available;
  const overflowIndex = nodes.length - positions.length;
  return { x: 52 + (overflowIndex % 6) * 258, y: 72 + (Math.floor(overflowIndex / 6) + 4) * 150 };
}

export function createNode(type, nodes, configuration = null) {
  if (!NODE_TYPES.has(type) || type === 'input') return null;
  const number = nodes.filter((node) => node.type === type).length + 1;
  const position = nextNodePosition(nodes);
  if (type === 'router') return { id: createWorkflowId('router'), type, name: `Router ${number}`, branches: [{ id: createWorkflowId('branch'), name: '分支 1' }, { id: createWorkflowId('branch'), name: '分支 2' }], ...position };
  if (type === 'output') return { id: createWorkflowId('output'), type, name: `Output ${number}`, workflowPorts: boundaryPorts(configuration?.output_ports), ...position };
  if (type === 'construct_message') return { id: createWorkflowId('construct-message'), type, name: `构造 Message ${number}`, role: 'user', ...position };
  if (type === 'construct_content') return { id: createWorkflowId('construct-content'), type, name: `构造 Content ${number}`, append_items: [{ type: 'fixed', value: '' }], dataInputPorts: [], ...position };
  if (type === 'construct_list') return { id: createWorkflowId('construct-list'), type, name: `构造列表 ${number}`, item_type: 'content', initial_value_count: 1, dataInputPorts: ['content-in-0'], ...position };
  if (type === 'foreach') return { id: createWorkflowId('foreach'), type, name: `遍历列表 ${number}`, item_type: 'content', ...position };
  if (type === 'history') return { id: createWorkflowId('history'), type, name: `召回 History ${number}`, event_types: ['terminal', 'response'], limit: 10, ...position };
  if (type === 'llm') return { id: createWorkflowId('llm'), type, name: `LLM ${number}`, model: '', prompt: '处理输入并返回结果。', dataInputPorts: ['message-in-0'], tools: [], think: false, tool_calls: false, ...position };
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