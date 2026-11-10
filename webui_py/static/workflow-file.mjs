// Structural detection only; execution validation remains with the Agent.
const object = (value) => value !== null && typeof value === 'object' && !Array.isArray(value);
const ports = (value) => Array.isArray(value) && value.every((port) => object(port)
  && typeof port.name === 'string' && typeof port.type === 'string');

export function parseWorkflowFile(content) {
  try {
    const workflow = JSON.parse(content);
    if (!object(workflow) || !['1.1', '1.2', '1.3', '1.4', '1.5', '1.6', '1.7', '2.0'].includes(workflow.schema_version)
      || typeof workflow.name !== 'string' || (workflow.description !== undefined && typeof workflow.description !== 'string')
      || !ports(workflow.input_ports) || !ports(workflow.output_ports)
      || !Array.isArray(workflow.nodes) || !workflow.nodes.every((node) => object(node) && typeof node.id === 'string')
      || !Array.isArray(workflow.connections) || !workflow.connections.every(object)) return null;
    for (const key of ['workflow_nodes', 'remote_tools']) {
      if (workflow[key] !== undefined && (!Array.isArray(workflow[key]) || !workflow[key].every((ref) => object(ref)
        && typeof (ref.name ?? ref.workflow_name) === 'string'
        && (ref.input_ports === undefined || ports(ref.input_ports))
        && (ref.output_ports === undefined || ports(ref.output_ports))))) return null;
    }
    return workflow;
  } catch {
    return null;
  }
}

// Build from the original document so swaps/overlapping names are remapped atomically.
export function editWorkflowMetadata(workflow, { name, description, dependencies }) {
  const next = { ...workflow, name };
  if (description !== (workflow.description || '')) next.description = description;
  const references = workflow.workflow_nodes || [];
  const replacements = new Map();
  if (references.some((ref, index) => (ref.name ?? ref.workflow_name) !== dependencies[index])) {
    next.workflow_nodes = references.map((ref, index) => {
      const previous = ref.name ?? ref.workflow_name;
      const name = dependencies[index];
      replacements.set(previous, name);
      return { ...ref, ...('name' in ref ? { name } : { workflow_name: name }) };
    });
    next.nodes = workflow.nodes.map((node) => {
      const previous = node.arguments?.workflow_name;
      if (node.type !== 'workflow' || !replacements.has(previous)) return node;
      return { ...node, arguments: { ...node.arguments, workflow_name: replacements.get(previous) } };
    });
  }
  return next;
}

export function validateWorkflowMetadata(workflow) {
  if (!workflow.name.trim()) throw new Error('Workflow 名称不能为空');
  const names = (workflow.workflow_nodes || []).map((ref) => ref.name ?? ref.workflow_name);
  if (names.some((name) => !name.trim())) throw new Error('依赖 Workflow 名称不能为空');
  if (new Set(names).size !== names.length) throw new Error('依赖 Workflow 名称不能重复');
}
