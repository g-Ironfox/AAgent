import { boundaryPorts, createNode, DATA_TYPES, NODE_TYPES, setNodeStructs } from './node-contract.js';
import { filterValidConnections } from './connection-rules.js';

export const WORKFLOW_SCHEMA_VERSION = '2.0';

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
  construct_message: new Set(['role', 'role_source']),
  construct_content: new Set(['append_items']),
  construct_map_content: new Set(['mappings']),
  construct_struct: new Set(['struct_id']),
  struct_get: new Set(['struct_id', 'field', 'missing', 'has_fallback']),
  struct_update: new Set(['struct_id', 'updates', 'remove_fields']),
  struct_to_json: new Set(['value_type']),
  json_to_struct: new Set(['value_type']),
  map_content_get: new Set(),
  deserialize_json: new Set(['outputs']),
  split_event: new Set(),
  publish_event: new Set(),
  construct_event: new Set(['event_type']),
  construct_list: new Set(['item_type', 'initial_value_count']),
  list_append: new Set(['item_type', 'position']),
  foreach: new Set(['item_type']),
  history: new Set(['event_types', 'limit']),
  llm: new Set(['model', 'think', 'tool_calls', 'tools']),
  local_tool: new Set(['tool', 'parameters']),
  remote_sync_tool: new Set(['tool', 'parameters', 'outputs', 'timeout_ms']),
  remote_async_tool: new Set(['tool', 'parameters', 'timeout_ms', 'callback']),
  context_create: new Set(['value_type', 'context_id']),
  context_read: new Set(['value_type', 'context_id_source', 'context_id']),
  context_write: new Set(['value_type', 'context_id_source', 'context_id']),
  session_create: new Set(['value_type']),
  session_read: new Set(['value_type']),
  session_write: new Set(['value_type']),
  workflow: new Set(['workflow_name']),
};
const NODE_ARGUMENT_FIELDS = new Set(Object.values(NODE_ARGUMENT_FIELDS_BY_TYPE).flatMap((fields) => [...fields]));

export function validateStructDefinitions(value) {
  if (!Array.isArray(value)) throw new Error('metadata.structs 必须是数组');
  const ids = new Set();
  const names = new Set();
  const definitions = new Map();
  for (const [index, item] of value.entries()) {
    if (!item || !['color,fields,id,name', 'color,fields,id,list_color,name'].includes(Object.keys(item).sort().join(','))
      || typeof item.id !== 'string' || !/^[A-Za-z_][A-Za-z0-9_]*$/.test(item.id) || ids.has(item.id)
      || typeof item.name !== 'string' || !item.name.trim() || names.has(item.name.toLocaleLowerCase())
      || typeof item.color !== 'string' || !/^#[0-9A-Fa-f]{6}$/.test(item.color)
      || (item.list_color !== undefined && (typeof item.list_color !== 'string' || !/^#[0-9A-Fa-f]{6}$/.test(item.list_color)))
      || !Array.isArray(item.fields)) throw new Error(`metadata.structs[${index}] 无效`);
    ids.add(item.id);
    names.add(item.name.toLocaleLowerCase());
    const fieldNames = new Set();
    for (const [fieldIndex, field] of item.fields.entries()) {
      if (!field || Object.keys(field).sort().join(',') !== 'name,required,type'
        || typeof field.name !== 'string' || !/^[A-Za-z_][A-Za-z0-9_]*$/.test(field.name) || fieldNames.has(field.name)
        || typeof field.type !== 'string' || typeof field.required !== 'boolean') throw new Error(`metadata.structs[${index}].fields[${fieldIndex}] 无效`);
      fieldNames.add(field.name);
    }
    definitions.set(item.id, item);
  }
  const visiting = new Set();
  const visited = new Set();
  const validType = (type) => DATA_TYPES.has(type)
    || /^struct:[A-Za-z_][A-Za-z0-9_]*$/.test(type)
    || /^list-struct:[A-Za-z_][A-Za-z0-9_]*$/.test(type);
  const visit = (id) => {
    if (visiting.has(id)) throw new Error(`Struct 类型依赖形成循环: ${id}`);
    if (visited.has(id)) return;
    visiting.add(id);
    const definition = definitions.get(id);
    for (const field of definition.fields) {
      if (!validType(field.type)) throw new Error(`Struct ${id} 字段 ${field.name} 类型无效`);
      const ref = /^(?:list-)?struct:(.+)$/.exec(field.type)?.[1];
      if (ref && !definitions.has(ref)) throw new Error(`Struct ${id} 引用了未声明类型 ${ref}`);
      if (ref) visit(ref);
    }
    visiting.delete(id);
    visited.add(id);
  };
  for (const id of definitions.keys()) visit(id);
  return structuredClone(value);
}

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
  metadata: { structs: [] },
  nodes: structuredClone(initialNodes),
  connections: structuredClone(initialConnections),
  input_ports: [{ name: 'origin', type: 'event' }],
  output_ports: [],
  workflow_nodes: [],
  remote_tools: [],
};

export function nodeById(id) {
  return state.nodes.find((node) => node.id === id);
}

export function addNode(type, configuration = null, viewport = null) {
  const node = createNode(type, state.nodes, { ...(configuration || {}), structs: state.metadata?.structs || [] }, viewport);
  if (!node) return null;
  setNodeStructs([node], state.metadata?.structs || []);
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
  state.metadata = { ...state.metadata, structs: validateStructDefinitions(state.metadata?.structs ?? []) };
  setNodeStructs(state.nodes, state.metadata.structs);
  return structuredClone({
    schema_version: WORKFLOW_SCHEMA_VERSION,
    name: state.name,
    description: state.description,
    metadata: state.metadata,
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
    schema_version: WORKFLOW_SCHEMA_VERSION,
    name: 'workflow',
    description: '',
    metadata: { structs: [] },
    input_ports: [{ name: 'origin', type: 'event' }],
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

function normalizeNode(node, inputPorts, outputPorts, callableWorkflows, remoteTools, structs) {
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
    if (!Array.isArray(node.branches)) return null;
    const branchIds = new Set();
    const branchNames = new Set();
    normalized.branches = [];
    for (const branch of node.branches) {
      if (!branch || typeof branch.id !== 'string' || !branch.id || branch.id === 'branch$others'
        || typeof branch.name !== 'string' || !branch.name || branchIds.has(branch.id) || branchNames.has(branch.name)
        || Object.keys(branch).some((key) => !['id', 'name'].includes(key))) return null;
      branchIds.add(branch.id);
      branchNames.add(branch.name);
      normalized.branches.push({ id: branch.id, name: branch.name });
    }
  }
  if (node.type === 'llm') {
    normalized.model = typeof node.model === 'string' ? node.model : 'gpt-5';
    normalized.think = node.think === true;
    normalized.tool_calls = node.tool_calls === true;
    normalized.tools = normalized.tool_calls && Array.isArray(node.tools) ? [...new Set(node.tools.filter((tool) => typeof tool === 'string' && tool))] : [];
  }
  if (node.type === 'construct_message') {
    normalized.role_source = ['fixed', 'port'].includes(node.role_source) ? node.role_source : 'fixed';
    normalized.role = ['user', 'system', 'assistant', 'tool'].includes(node.role) ? node.role : 'user';
  }
  if (node.type === 'construct_content') {
    normalized.append_items = Array.isArray(node.append_items) && node.append_items.length
      ? node.append_items.flatMap((item, index) => item?.type === 'port'
        ? [{ type: 'port', port_id: typeof item.port_id === 'string' && item.port_id ? item.port_id : `append-in-${index}` }]
        : item?.type === 'fixed' ? [{ type: 'fixed', value: typeof item.value === 'string' ? item.value.slice(0, 100000) : '' }] : [])
      : [{ type: 'port', port_id: 'append-in-0' }];
    normalized.dataInputPorts = normalized.append_items.filter((item) => item.type === 'port').map((item) => item.port_id);
  }
  if (node.type === 'construct_map_content') {
    if (!Array.isArray(node.mappings) || !node.mappings.length) return null;
    const keys = new Set();
    const portIds = new Set();
    normalized.mappings = [];
    for (const item of node.mappings) {
      if (!item || typeof item.key !== 'string' || !item.key || keys.has(item.key)) return null;
      keys.add(item.key);
      if (item.value_source === 'port') {
        if (Object.keys(item).length !== 3 || typeof item.port_id !== 'string' || !item.port_id || ['control-in', 'control-out'].includes(item.port_id) || portIds.has(item.port_id)) return null;
        portIds.add(item.port_id);
        normalized.mappings.push({ key: item.key, value_source: 'port', port_id: item.port_id });
      } else {
        if (typeof item.value !== 'string' || ![undefined, 'fixed'].includes(item.value_source) || Object.keys(item).some((key) => !['key', 'value', 'value_source'].includes(key))) return null;
        normalized.mappings.push({ key: item.key, value: item.value });
      }
    }
    if (node.dataInputPorts !== undefined && (!Array.isArray(node.dataInputPorts) || node.dataInputPorts.length !== portIds.size || node.dataInputPorts.some((id) => !portIds.has(id)) || new Set(node.dataInputPorts).size !== portIds.size)) return null;
    if (portIds.size && node.dataInputPorts === undefined) return null;
    normalized.dataInputPorts = [...portIds];
  }
  if (node.type === 'construct_struct' || node.type === 'struct_get' || node.type === 'struct_update') {
    if (node.struct_id === '') {
      normalized.struct_id = '';
      if (node.type === 'construct_struct') normalized.dataInputPorts = [];
      if (node.type === 'struct_get') Object.assign(normalized, { field: '', missing: 'error', has_fallback: false, dataInputPorts: [] });
      if (node.type === 'struct_update') Object.assign(normalized, { updates: [], remove_fields: [], dataInputPorts: [] });
    } else {
    if (typeof node.struct_id !== 'string' || !/^[A-Za-z_][A-Za-z0-9_]*$/.test(node.struct_id)) return null;
    normalized.struct_id = node.struct_id;
    const definition = (structs || []).find((item) => item.id === node.struct_id);
    if (!definition) return null;
    const fields = new Map(definition.fields.map((field) => [field.name, field]));
    if (node.type === 'construct_struct') normalized.dataInputPorts = definition.fields.map((field) => field.name);
    if (node.type === 'struct_get') {
      const fieldName = node.field || definition.fields[0]?.name || '';
      if (fieldName && !fields.has(fieldName)) return null;
      normalized.field = fieldName;
      normalized.missing = node.missing === 'fallback' ? 'fallback' : 'error';
      normalized.has_fallback = normalized.missing === 'fallback';
      if (normalized.has_fallback && (!fieldName || fields.get(fieldName).required)) return null;
      normalized.dataInputPorts = normalized.has_fallback ? ['struct-in', 'fallback-in'] : ['struct-in'];
    }
    if (node.type === 'struct_update') {
      if (!Array.isArray(node.updates) || !Array.isArray(node.remove_fields)
        || [...node.updates, ...node.remove_fields].some((name) => !fields.has(name))
        || new Set(node.updates).size !== node.updates.length
        || new Set(node.remove_fields).size !== node.remove_fields.length
        || node.updates.some((name) => node.remove_fields.includes(name))) return null;
      normalized.updates = [...node.updates];
      normalized.remove_fields = [...node.remove_fields];
      normalized.dataInputPorts = ['struct-in', ...node.updates];
    }
    }
  }
  if (node.type === 'struct_to_json' || node.type === 'json_to_struct') {
    if (node.value_type === '') {
      normalized.value_type = '';
    } else {
    if (typeof node.value_type !== 'string' || !/^(?:list-)?struct:[A-Za-z_][A-Za-z0-9_]*$/.test(node.value_type)) return null;
    const typeId = node.value_type.replace(/^list-/, '').slice('struct:'.length);
    if (!(structs || []).some((item) => item.id === typeId)) return null;
    normalized.value_type = node.value_type;
    }
  }
  if (node.type === 'deserialize_json') {
    if (!Array.isArray(node.outputs) || !node.outputs.length) return null;
    const outputKeys = new Set();
    normalized.outputs = [];
    for (const output of node.outputs) {
      if (
        !output
        || typeof output !== 'object'
        || Object.keys(output).length !== 2
        || typeof output.key !== 'string'
        || !output.key
        || output.key === 'control-out'
        || outputKeys.has(output.key)
        || !['content', 'message', 'event', 'map-content', 'list-content', 'list-message', 'list-event'].includes(output.type)
      ) return null;
      outputKeys.add(output.key);
      normalized.outputs.push({ key: output.key, type: output.type });
    }
  }
  if (node.type === 'construct_list') {
    normalized.item_type = (['content', 'message', 'event'].includes(node.item_type) || /^struct:[A-Za-z_][A-Za-z0-9_]*$/.test(node.item_type || '')) ? node.item_type : 'content';
    normalized.initial_value_count = Number.isInteger(node.initial_value_count) ? Math.min(20, Math.max(0, node.initial_value_count)) : 1;
    normalized.dataInputPorts = Array.from({ length: normalized.initial_value_count }, (_, index) => `${normalized.item_type}-in-${index}`);
  }
  if (node.type === 'list_append') {
    normalized.item_type = (['content', 'message', 'event'].includes(node.item_type) || /^struct:[A-Za-z_][A-Za-z0-9_]*$/.test(node.item_type || '')) ? node.item_type : 'content';
    normalized.position = ['start', 'end'].includes(node.position) ? node.position : 'end';
  }
  if (node.type === 'foreach') normalized.item_type = (['content', 'message', 'event'].includes(node.item_type) || /^struct:[A-Za-z_][A-Za-z0-9_]*$/.test(node.item_type || '')) ? node.item_type : 'content';
  if (node.type === 'history') {
    normalized.event_types = Array.isArray(node.event_types)
      ? [...new Set(node.event_types.filter((eventType) => ['terminal', 'response'].includes(eventType)))]
      : [];
    if (!normalized.event_types.length) return null;
    normalized.limit = Number.isInteger(node.limit) ? Math.min(1000, Math.max(1, node.limit)) : 10;
  }
  if (['context_create', 'context_read', 'context_write', 'session_create', 'session_read', 'session_write'].includes(node.type)) {
    if (!['content', 'message', 'event', 'map-content', 'list-content', 'list-message', 'list-event'].includes(node.value_type)
      && !((node.type.startsWith('context_')) && /^(?:list-)?struct:[A-Za-z_][A-Za-z0-9_]*$/.test(node.value_type || '')
        && (structs || []).some((item) => item.id === node.value_type.replace(/^list-/, '').slice('struct:'.length)))) return null;
    normalized.value_type = node.value_type;
  }
  if (node.type === 'context_read' || node.type === 'context_write') {
    normalized.context_id_source = node.context_id_source === 'fixed' ? 'fixed' : 'port';
    if (normalized.context_id_source === 'fixed') {
      if (typeof node.context_id !== 'string' || !node.context_id.trim()) return null;
      normalized.context_id = node.context_id;
    }
  }
  if (node.type === 'context_create' && node.context_id) {
    if (typeof node.context_id !== 'string' || !node.context_id.trim()) return null;
    normalized.context_id = node.context_id;
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
          || !['content', 'message', 'event', 'map-content', 'list-content', 'list-message', 'list-event'].includes(parameter.type)
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
            || !['content', 'message', 'event', 'map-content', 'list-content', 'list-message', 'list-event'].includes(output.type)
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

export function migrateWorkflowToCurrentVersion(workflow) {
  if (!['1.6', '1.7'].includes(workflow?.schema_version)) return workflow;
  const migrated = structuredClone(workflow);
  migrated.schema_version = WORKFLOW_SCHEMA_VERSION;
  for (const node of migrated.nodes || []) {
    if (node?.type !== 'router') continue;
    if (!node.arguments || typeof node.arguments !== 'object' || Array.isArray(node.arguments)
      || !Array.isArray(node.arguments.branches)) continue;
    node.arguments.branches = node.arguments.branches.filter((branch) => branch?.id !== 'branch$others');
  }
  return migrated;
}

export function loadSnapshot(saved, metadata = null) {
  try {
    saved = migrateWorkflowToCurrentVersion(saved);
    if (saved?.schema_version !== WORKFLOW_SCHEMA_VERSION) return false;
    const savedNodes = Array.isArray(saved) ? saved : saved?.nodes;
    if (!Array.isArray(savedNodes)) return false;
    const workflowName = metadata?.name ?? saved?.name;
    if (typeof workflowName !== 'string' || !workflowName.trim()) return false;
    const inputPorts = boundaryPorts(metadata?.input_ports ?? saved?.input_ports);
    const outputPorts = boundaryPorts(metadata?.output_ports ?? saved?.output_ports);
    const structDefinitions = validateStructDefinitions(saved?.metadata?.structs ?? []);
    const workflowNodes = callableWorkflowMetadata(saved);
    const callableWorkflows = new Map(workflowNodes.map((workflow) => [workflow.name, workflow]));
    const remoteTools = remoteToolMetadata(saved);
    const remoteToolsByName = new Map(remoteTools.map((tool) => [tool.name, tool]));
    const ids = new Set();
    const nodes = [];
    for (const node of savedNodes) {
      if (!node || typeof node.id !== 'string' || ids.has(node.id) || !NODE_TYPES.has(node.type) || !hasStrictNodeFormat(node)) return false;
      ids.add(node.id);
      const normalized = normalizeNode(node, inputPorts, outputPorts, callableWorkflows, remoteToolsByName, structDefinitions);
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
    state.metadata = { ...(saved?.metadata ?? {}), structs: structDefinitions };
    setNodeStructs(nodes, state.metadata.structs);
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
  const workflow = migrateWorkflowToCurrentVersion(normalizeImportedWorkflow(JSON.parse(text)));
  if (!workflow || typeof workflow !== 'object' || Array.isArray(workflow)) throw new Error('内容不是有效的 Workflow JSON');
  if (workflow.schema_version !== WORKFLOW_SCHEMA_VERSION) throw new Error(`Workflow schema_version 必须是 ${WORKFLOW_SCHEMA_VERSION}`);
  if (typeof workflow.name !== 'string' || !workflow.name.trim()) throw new Error('Workflow 名称不能为空');
  if (!Array.isArray(workflow.nodes) || !Array.isArray(workflow.connections)) throw new Error('Workflow 缺少节点或连接数据');
  return workflow;
}
