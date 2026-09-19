import { boundaryPorts, createNode, createWorkflowId, NODE_TYPES } from './node-contract.js';
import { filterValidConnections } from './connection-rules.js';

const initialNodes = [
  { id: 'input', type: 'input', name: 'Input', x: 52, y: 238 },
  { id: 'output', type: 'output', name: 'Output', x: 310, y: 238 },
];
const initialConnections = [
  { id: 'control-input-output', fromId: 'input', fromPortId: 'control-out', toId: 'output', toPortId: 'control-in', type: 'control' },
];

const NODE_BASE_FIELDS = new Set(['id', 'type', 'name', 'x', 'y', 'arguments']);
const NODE_SHARED_FIELDS = new Set(['workflowPorts', 'dataInputPorts', 'input_ports', 'output_ports']);
const NODE_ARGUMENT_FIELDS_BY_TYPE = {
  input: new Set(),
  output: new Set(),
  router: new Set(['branches']),
  construct_message: new Set(['role']),
  construct_content: new Set(['append_items']),
  split_event: new Set(),
  construct_list: new Set(['item_type', 'initial_value_count']),
  list_append: new Set(['item_type', 'position']),
  foreach: new Set(['item_type']),
  history: new Set(['event_types', 'limit']),
  llm: new Set(['model', 'think', 'tool_calls', 'tools']),
  local_tool: new Set(['tool', 'parameters']),
  remote_sync_tool: new Set(['tool', 'parameters', 'outputs', 'timeout_ms']),
  remote_async_tool: new Set(['tool', 'parameters', 'timeout_ms', 'callback']),
  context_create: new Set(['value_type']),
  context_read: new Set(['value_type']),
  context_write: new Set(['value_type']),
  workflow: new Set(['workflow_name']),
};
const NODE_ARGUMENT_FIELDS = new Set(Object.values(NODE_ARGUMENT_FIELDS_BY_TYPE).flatMap((fields) => [...fields]));

function hasStrictNodeFormat(node) {
  const argumentsValue = node.arguments ?? {};
  if (!argumentsValue || typeof argumentsValue !== 'object' || Array.isArray(argumentsValue)) return false;
  if (Object.keys(node).some((key) => NODE_ARGUMENT_FIELDS.has(key))) return false;
  if (Object.keys(argumentsValue).some((key) => NODE_SHARED_FIELDS.has(key))) return false;
  if (Object.keys(argumentsValue).some((key) => !NODE_ARGUMENT_FIELDS_BY_TYPE[node.type]?.has(key))) return false;
  return Object.keys(node).every((key) => NODE_BASE_FIELDS.has(key) || NODE_SHARED_FIELDS.has(key));
}

function expandNodeArguments(node) {
  const argumentsValue = node?.arguments && typeof node.arguments === 'object' && !Array.isArray(node.arguments)
    ? node.arguments
    : {};
  const expanded = { ...argumentsValue, ...node };
  delete expanded.arguments;
  return expanded;
}

function compactNodeArguments(node) {
  const argumentsValue = Object.fromEntries(
    Object.entries(node).filter(([key]) => NODE_ARGUMENT_FIELDS.has(key)),
  );
  return {
    ...Object.fromEntries(Object.entries(node).filter(([key]) => NODE_BASE_FIELDS.has(key) && key !== 'arguments')),
    ...Object.fromEntries(Object.entries(node).filter(([key]) => NODE_SHARED_FIELDS.has(key))),
    arguments: argumentsValue,
  };
}

export const state = {
  name: 'workflow',
  description: '',
  nodes: structuredClone(initialNodes),
  connections: structuredClone(initialConnections),
  input_ports: [],
  output_ports: [],
  workflow_nodes: [],
  remote_tools: [],
};

export function nodeById(id) {
  return state.nodes.find((node) => node.id === id);
}

export function addNode(type, configuration = null) {
  const node = createNode(type, state.nodes, configuration);
  if (!node) return null;
  state.nodes.push(node);
  return node;
}

export function deleteNode(id) {
  if (id === 'input') return false;
  state.nodes = state.nodes.filter((node) => node.id !== id);
  state.connections = state.connections.filter((connection) => connection.fromId !== id && connection.toId !== id);
  return true;
}

export function workflowSnapshot() {
  return structuredClone({
    name: state.name,
    description: state.description,
    input_ports: state.input_ports,
    output_ports: state.output_ports,
    workflow_nodes: state.workflow_nodes,
    remote_tools: state.remote_tools,
    nodes: state.nodes.map(compactNodeArguments),
    connections: state.connections,
  });
}

export function resetWorkflow() {
  return loadSnapshot({
    name: 'workflow',
    description: '',
    input_ports: [],
    output_ports: [],
    workflow_nodes: [],
    remote_tools: [],
    nodes: initialNodes,
    connections: initialConnections,
  });
}

function callableWorkflowMetadata(saved) {
  const declarations = Array.isArray(saved?.workflow_nodes) ? saved.workflow_nodes : [];
  const names = new Set();
  return declarations.flatMap((workflow) => {
    const name = typeof workflow?.name === 'string' && workflow.name.trim()
      ? workflow.name.trim().slice(0, 120)
      : '';
    const normalizedName = name.toLocaleLowerCase();
    if (!name || names.has(normalizedName)) return [];
    names.add(normalizedName);
    return [{
      name,
      input_ports: boundaryPorts(workflow.input_ports).map(({ id, ...port }) => port),
      output_ports: boundaryPorts(workflow.output_ports).map(({ id, ...port }) => port),
    }];
  });
}

function remoteToolMetadata(saved) {
  const declarations = Array.isArray(saved?.remote_tools) ? saved.remote_tools : [];
  const names = new Set();
  return declarations.flatMap((tool) => {
    const name = typeof tool?.name === 'string' && tool.name.trim()
      ? tool.name.trim().slice(0, 128)
      : '';
    const normalizedName = name.toLocaleLowerCase();
    if (!name || names.has(normalizedName)) return [];
    names.add(normalizedName);
    return [{
      name,
      input_ports: boundaryPorts(tool.input_ports).map(({ id, ...port }) => port),
      output_ports: boundaryPorts(tool.output_ports).map(({ id, ...port }) => port),
    }];
  });
}

function normalizeNode(node, inputPorts, outputPorts, callableWorkflows, remoteTools) {
  node = expandNodeArguments(node);
  const normalized = {
    id: node.id,
    type: node.type,
    name: typeof node.name === 'string' ? node.name.slice(0, 30) : node.type.toUpperCase(),
    x: Number.isFinite(node.x) ? Math.max(12, node.x) : 52,
    y: Number.isFinite(node.y) ? Math.max(12, node.y) : 72,
  };
  if (node.type === 'input' || node.type === 'output') {
    normalized.workflowPorts = structuredClone(node.type === 'input' ? inputPorts : outputPorts);
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
    normalized.think = node.think === true;
    normalized.tool_calls = node.tool_calls === true;
    normalized.tools = normalized.tool_calls && Array.isArray(node.tools) ? [...new Set(node.tools.filter((tool) => typeof tool === 'string' && tool))] : [];
  }
  if (node.type === 'construct_message') normalized.role = ['user', 'system', 'assistant'].includes(node.role) ? node.role : 'user';
  if (node.type === 'construct_content') {
    normalized.append_items = Array.isArray(node.append_items) && node.append_items.length
      ? node.append_items.flatMap((item, index) => item?.type === 'port'
        ? [{ type: 'port', port_id: typeof item.port_id === 'string' && item.port_id ? item.port_id : `append-in-${index}` }]
        : item?.type === 'fixed' ? [{ type: 'fixed', value: typeof item.value === 'string' ? item.value.slice(0, 100000) : '' }] : [])
      : [{ type: 'port', port_id: 'append-in-0' }];
    normalized.dataInputPorts = normalized.append_items.filter((item) => item.type === 'port').map((item) => item.port_id);
  }
  if (node.type === 'construct_list') {
    normalized.item_type = ['content', 'message', 'event'].includes(node.item_type) ? node.item_type : 'content';
    normalized.initial_value_count = Number.isInteger(node.initial_value_count) ? Math.min(20, Math.max(0, node.initial_value_count)) : 1;
    normalized.dataInputPorts = Array.from({ length: normalized.initial_value_count }, (_, index) => `${normalized.item_type}-in-${index}`);
  }
  if (node.type === 'list_append') {
    normalized.item_type = ['content', 'message', 'event'].includes(node.item_type) ? node.item_type : 'content';
    normalized.position = ['start', 'end'].includes(node.position) ? node.position : 'end';
  }
  if (node.type === 'foreach') normalized.item_type = ['content', 'message', 'event'].includes(node.item_type) ? node.item_type : 'content';
  if (node.type === 'history') {
    normalized.event_types = Array.isArray(node.event_types)
      ? [...new Set(node.event_types.filter((eventType) => ['terminal', 'response'].includes(eventType)))]
      : [];
    if (!normalized.event_types.length) return null;
    normalized.limit = Number.isInteger(node.limit) ? Math.min(1000, Math.max(1, node.limit)) : 10;
  }
  if (['context_create', 'context_read', 'context_write'].includes(node.type)) {
    if (!['content', 'message', 'event', 'list-content', 'list-message', 'event-list'].includes(node.value_type)) return null;
    normalized.value_type = node.value_type;
  }
  if (['local_tool', 'remote_sync_tool', 'remote_async_tool'].includes(node.type)) {
    normalized.tool = typeof node.tool === 'string' ? node.tool : '';
    if (node.type === 'local_tool') {
      normalized.parameters = Array.isArray(node.parameters)
        ? [...new Set(node.parameters.filter((parameter) => typeof parameter === 'string' && parameter && parameter !== 'control-in'))]
        : [];
    } else {
      const declaration = remoteTools.get(normalized.tool);
      if (normalized.tool && !declaration) return null;
      if (!Array.isArray(node.parameters)) return null;
      const parameterNames = new Set();
      normalized.parameters = [];
      for (const parameter of node.parameters) {
        if (
          !parameter
          || typeof parameter !== 'object'
          || Object.keys(parameter).length !== 2
          || typeof parameter.name !== 'string'
          || !parameter.name
          || parameter.name === 'control-in'
          || parameterNames.has(parameter.name)
          || !['content', 'message', 'event', 'list-content', 'list-message', 'event-list'].includes(parameter.type)
        ) return null;
        parameterNames.add(parameter.name);
        normalized.parameters.push({ name: parameter.name, type: parameter.type });
      }
      if (declaration) normalized.parameters = structuredClone(declaration.input_ports);
      if (node.type === 'remote_sync_tool') {
        if (!Array.isArray(node.outputs)) return null;
        const outputNames = new Set();
        normalized.outputs = [];
        for (const output of node.outputs) {
          if (
            !output
            || typeof output !== 'object'
            || Object.keys(output).length !== 2
            || typeof output.name !== 'string'
            || !output.name
            || output.name === 'control-out'
            || outputNames.has(output.name)
            || !['content', 'message', 'event', 'list-content', 'list-message', 'event-list'].includes(output.type)
          ) return null;
          outputNames.add(output.name);
          normalized.outputs.push({ name: output.name, type: output.type });
        }
        if (declaration) normalized.outputs = structuredClone(declaration.output_ports);
      }
      const defaultTimeoutMs = node.type === 'remote_async_tool' ? 600000 : 10000;
      normalized.timeout_ms = Number.isInteger(node.timeout_ms) && node.timeout_ms > 0 ? node.timeout_ms : defaultTimeoutMs;
      if (node.type === 'remote_async_tool') {
        const callback = node.callback;
        if (callback == null) normalized.callback = null;
        else {
          if (
            typeof callback !== 'object'
            || Array.isArray(callback)
            || Object.keys(callback).length !== 4
            || callback.type !== 'redis'
            || typeof callback.queue !== 'string'
            || !callback.queue
            || callback.queue.length > 256
            || typeof callback.event_type !== 'string'
            || !callback.event_type
            || callback.event_type.length > 128
            || !Array.isArray(callback.on)
            || !callback.on.length
            || callback.on.length !== new Set(callback.on).size
            || callback.on.some((status) => !['working', 'completed', 'failed'].includes(status))
          ) return null;
          normalized.callback = {
            type: 'redis',
            queue: callback.queue,
            event_type: callback.event_type,
            on: [...callback.on],
          };
        }
      }
    }
  }
  if (node.type === 'workflow') {
    const workflowName = typeof node.workflow_name === 'string' && node.workflow_name.trim()
      ? node.workflow_name.trim().slice(0, 120)
      : '';
    if (!workflowName) return null;
    const declaration = callableWorkflows.get(workflowName);
    normalized.workflow_name = declaration?.name || workflowName;
    normalized.input_ports = structuredClone(declaration?.input_ports || boundaryPorts(node.input_ports).map(({ id, ...port }) => port));
    normalized.output_ports = structuredClone(declaration?.output_ports || boundaryPorts(node.output_ports).map(({ id, ...port }) => port));
  }
  return normalized;
}

export function loadSnapshot(saved, metadata = null) {
  try {
    const savedNodes = Array.isArray(saved) ? saved : saved?.nodes;
    if (!Array.isArray(savedNodes)) return false;
    const workflowName = metadata?.name ?? saved?.name;
    if (typeof workflowName !== 'string' || !workflowName.trim()) return false;
    const inputPorts = boundaryPorts(metadata?.input_ports ?? saved?.input_ports);
    const outputPorts = boundaryPorts(metadata?.output_ports ?? saved?.output_ports);
    const workflowNodes = callableWorkflowMetadata(saved);
    const callableWorkflows = new Map(workflowNodes.map((workflow) => [workflow.name, workflow]));
    const remoteTools = remoteToolMetadata(saved);
    const remoteToolsByName = new Map(remoteTools.map((tool) => [tool.name, tool]));
    const ids = new Set();
    const nodes = [];
    for (const node of savedNodes) {
      if (!node || typeof node.id !== 'string' || ids.has(node.id) || !NODE_TYPES.has(node.type) || !hasStrictNodeFormat(node)) return false;
      ids.add(node.id);
      const normalized = normalizeNode(node, inputPorts, outputPorts, callableWorkflows, remoteToolsByName);
      if (!normalized) return false;
      nodes.push(normalized);
    }
    if (!nodes.some((node) => node.id === 'input' && node.type === 'input')) return false;
    if (!nodes.some((node) => node.type === 'output')) {
      const output = createNode('output', nodes, { output_ports: outputPorts.map(({ id, ...port }) => port) });
      if (output) nodes.push(output);
    }
    state.name = workflowName.trim().slice(0, 120);
    const description = metadata?.description ?? saved?.description;
    state.description = typeof description === 'string' ? description.trim().slice(0, 2000) : '';
    state.input_ports = inputPorts.map(({ id, ...port }) => port);
    state.output_ports = outputPorts.map(({ id, ...port }) => port);
    state.workflow_nodes = workflowNodes;
    state.remote_tools = remoteTools;
    state.nodes = nodes;
    state.connections = filterValidConnections(Array.isArray(saved?.connections) ? saved.connections : initialConnections, nodes);
    return true;
  } catch (error) {
    console.warn('Workflow 数据读取失败', error);
    return false;
  }
}

export function normalizeImportedWorkflow(imported) {
  if (!imported?.workflows || typeof imported.workflows !== 'object' || Array.isArray(imported.workflows)) return imported;
  const entries = Object.entries(imported.workflows);
  const main = typeof imported.main === 'string' && imported.workflows[imported.main] ? imported.main : entries[0]?.[0];
  if (!main) throw new Error('Workflow 集合为空');
  return {
    ...imported.workflows[main],
    name: imported.workflows[main].name || main,
    workflow_nodes: entries
      .filter(([name]) => name !== main)
      .map(([name, callable]) => ({ name, input_ports: callable.input_ports || [], output_ports: callable.output_ports || [] })),
    remote_tools: imported.workflows[main].remote_tools || [],
  };
}

export function parseWorkflowText(text) {
  const workflow = normalizeImportedWorkflow(JSON.parse(text));
  if (!workflow || typeof workflow !== 'object' || Array.isArray(workflow)) throw new Error('内容不是有效的 Workflow JSON');
  if (typeof workflow.name !== 'string' || !workflow.name.trim()) throw new Error('Workflow 名称不能为空');
  if (!Array.isArray(workflow.nodes) || !Array.isArray(workflow.connections)) throw new Error('Workflow 缺少节点或连接数据');
  return workflow;
}