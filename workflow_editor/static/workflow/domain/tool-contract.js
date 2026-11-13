import { DATA_TYPES } from './node-contract.js';

export function toolFromSchema(schema, kind) {
  const workflowType = (value) => DATA_TYPES.has(value?.['x-workflow-port-type'])
    ? value['x-workflow-port-type'] : value?.type === 'array' ? 'list-content' : 'content';
  const ports = (value, fallback = null) => {
    if (!value || typeof value !== 'object') return [];
    if (value.properties && typeof value.properties === 'object') {
      return Object.entries(value.properties).map(([name, item]) => ({ name, type: workflowType(item) }));
    }
    return fallback ? [{ name: fallback, type: workflowType(value) }] : [];
  };
  return {
    name: schema.name, kind,
    input_ports: kind === 'local'
      ? Object.keys(schema.inputSchema?.properties || {}).map((name) => ({ name, type: 'content' }))
      : ports(schema.inputSchema),
    output_ports: kind === 'local' ? [{ name: 'output', type: 'content' }] : ports(schema.outputSchema, 'result'),
  };
}

export function applyToolDeclaration(node, declaration) {
  if (node.type === 'remote_async_tool' && declaration.kind !== 'remote') {
    throw new Error('异步 Tool 只能使用 Remote Tool');
  }
  node.tool = declaration.name;
  node.parameters = structuredClone(declaration.input_ports);
  if (node.type === 'remote_async_tool') {
    delete node.mode;
    delete node.outputs;
  } else {
    node.outputs = structuredClone(declaration.output_ports);
    if (node.mode !== 'sync' || declaration.kind === 'local') {
      node.timeout_ms = 10000;
    }
    node.mode = 'sync';
    node.callback = null;
  }
}
