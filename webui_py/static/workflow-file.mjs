// Structural detection only; execution validation remains with the Agent.
const object = (value) => value !== null && typeof value === 'object' && !Array.isArray(value);
const ports = (value) => Array.isArray(value) && value.every((port) => object(port)
  && typeof port.name === 'string' && typeof port.type === 'string');

export function parseWorkflowFile(content) {
  try {
    const workflow = migrateSubprocessWorkflowFormat(JSON.parse(content));
    if (!object(workflow) || !['1.1', '1.2', '1.3', '1.4', '1.5', '1.6', '1.7', '2.0'].includes(workflow.schema_version)
      || (workflow.description !== undefined && typeof workflow.description !== 'string')
      || !ports(workflow.input_ports) || !ports(workflow.output_ports)
      || !Array.isArray(workflow.nodes) || !workflow.nodes.every((node) => object(node) && typeof node.id === 'string')
      || !Array.isArray(workflow.connections) || !workflow.connections.every(object)) return null;
    for (const key of ['remote_tools']) {
      if (workflow[key] !== undefined && (!Array.isArray(workflow[key]) || !workflow[key].every((ref) => object(ref)
        && typeof ref.name === 'string'
        && (ref.input_ports === undefined || ports(ref.input_ports))
        && (ref.output_ports === undefined || ports(ref.output_ports))))) return null;
    }
    return workflow;
  } catch {
    return null;
  }
}

export function editWorkflowMetadata(workflow, { description }) {
  const next = migrateSubprocessWorkflowFormat(workflow);
  if (description !== (next.description || '')) next.description = description;
  return next;
}

export function validateWorkflowMetadata(workflow) {
  if (workflow.description !== undefined && typeof workflow.description !== 'string') throw new Error('Workflow 描述必须是文本');
}

export function migrateSubprocessWorkflowFormat(workflow) {
  if (!workflow || typeof workflow !== 'object' || Array.isArray(workflow)) return workflow;
  const next = structuredClone(workflow);
  delete next.name;
  if (next.metadata && typeof next.metadata === 'object' && !Array.isArray(next.metadata)) delete next.metadata.name;
  delete next.workflow_nodes;
  delete next.subprocess_workflow_files;
  for (const node of next.nodes || []) {
    if (!node || !['workflow', 'spawn_and_wait_subprocess'].includes(node.type)) continue;
    node.type = 'spawn_and_wait_subprocess';
    for (const args of [node, node.arguments]) {
      if (!args || !Object.hasOwn(args, 'workflow_name')) continue;
      if (Object.hasOwn(args, 'workflow_file') && args.workflow_file !== args.workflow_name) throw new Error('Conflicting workflow_name and workflow_file');
      args.workflow_file = args.workflow_name;
      delete args.workflow_name;
    }
  }
  return next;
}
