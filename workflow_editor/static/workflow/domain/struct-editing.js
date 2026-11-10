import { validateStructDefinitions } from './serialization.js';

export function prepareStructDefinitions(draft) {
  const idMap = new Map();
  const names = new Set();
  for (const definition of draft) {
    const name = definition.name.trim();
    if (!/^[A-Za-z_][A-Za-z0-9_]{0,79}$/.test(name)) {
      throw new Error('Struct 名称须以字母或下划线开头，仅包含字母、数字和下划线，最多 80 个字符');
    }
    const key = name.toLowerCase();
    if (names.has(key)) throw new Error(`Struct 名称不能重复：${name}`);
    names.add(key);
    idMap.set(definition.id, name);
  }
  const structs = draft.map((definition) => ({
    ...definition,
    id: idMap.get(definition.id),
    name: idMap.get(definition.id),
    fields: definition.fields.map((field) => ({ ...field, type: remapStructType(field.type, idMap) })),
  }));
  return { structs: validateStructDefinitions(structs), idMap };
}

function remapStructType(type, idMap) {
  const match = /^(list-struct:|struct:)(.+)$/.exec(type || '');
  return match && idMap.has(match[2]) ? `${match[1]}${idMap.get(match[2])}` : type;
}

// Only rewrite type-bearing properties, never user data or node/connection IDs.
export function remapStructReferences(workflow, idMap) {
  const remapPorts = (ports) => {
    for (const port of ports || []) {
      if (port && typeof port === 'object' && typeof port.type === 'string') {
        port.type = remapStructType(port.type, idMap);
      }
    }
  };
  const listPortIds = new Map();
  remapPorts(workflow.input_ports);
  remapPorts(workflow.output_ports);
  for (const reference of [...(workflow.workflow_nodes || []), ...(workflow.remote_tools || [])]) {
    remapPorts(reference.input_ports);
    remapPorts(reference.output_ports);
  }
  for (const node of workflow.nodes || []) {
    const args = node.arguments || node;
    const previousItemType = args.item_type;
    if (idMap.has(args.struct_id)) args.struct_id = idMap.get(args.struct_id);
    for (const key of ['value_type', 'item_type']) {
      if (typeof args[key] === 'string') args[key] = remapStructType(args[key], idMap);
    }
    remapPorts(args.parameters);
    remapPorts(args.outputs);
    remapPorts(args.input_ports);
    remapPorts(args.output_ports);
    if (args !== node) {
      remapPorts(node.input_ports);
      remapPorts(node.output_ports);
    }
    if (node.type === 'construct_list' && previousItemType !== args.item_type) {
      const portMap = new Map((node.dataInputPorts || []).map((id) => [id, id.replace(`${previousItemType}-in-`, `${args.item_type}-in-`)]));
      node.dataInputPorts = (node.dataInputPorts || []).map((id) => portMap.get(id));
      listPortIds.set(node.id, portMap);
    }
  }
  remapPorts(workflow.connections);
  for (const connection of workflow.connections || []) {
    const portMap = listPortIds.get(connection.toId);
    if (portMap?.has(connection.toPortId)) connection.toPortId = portMap.get(connection.toPortId);
  }
}
