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
    for (const key of ['subprocess_workflow_files', 'remote_tools']) {
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

// Build from the original document so swaps/overlapping names are remapped atomically.
export function editWorkflowMetadata(workflow, { description, subprocessFiles }) {
  workflow = migrateSubprocessWorkflowFormat(workflow);
  const next = { ...workflow };
  if (description !== (workflow.description || '')) next.description = description;
  const references = workflow.subprocess_workflow_files || [];
  const replacements = new Map();
  if (references.some((ref, index) => ref.name !== subprocessFiles[index])) {
    next.subprocess_workflow_files = references.map((ref, index) => {
      const previous = ref.name;
      const name = subprocessFiles[index];
      replacements.set(previous, name);
      return { ...ref, name };
    });
    next.nodes = workflow.nodes.map((node) => {
      const previous = node.arguments?.workflow_file;
      if (node.type !== "spawn_and_wait_subprocess" || !replacements.has(previous)) return node;
      return { ...node, arguments: { ...node.arguments, workflow_file: replacements.get(previous) } };
    });
  }
  return next;
}

export function validateWorkflowMetadata(workflow) {
  const names = (workflow.subprocess_workflow_files || []).map((ref) => ref.name);
  if (names.some((name) => !name.trim())) throw new Error('子进程 Workflow 文件名不能为空');
  if (new Set(names).size !== names.length) throw new Error('子进程 Workflow 文件名不能重复');
}

export function migrateSubprocessWorkflowFormat(workflow) {
  if (!workflow || typeof workflow !== 'object' || Array.isArray(workflow)) return workflow;
  const next = structuredClone(workflow);
  delete next.name;
  if (next.metadata && typeof next.metadata === 'object' && !Array.isArray(next.metadata)) delete next.metadata.name;
  const stable = (value) => JSON.stringify(value, (_, item) => item && typeof item === 'object' && !Array.isArray(item)
    ? Object.fromEntries(Object.entries(item).sort(([left], [right]) => left.localeCompare(right))) : item);
  if (Object.hasOwn(next, 'workflow_nodes')) {
    if (Object.hasOwn(next, 'subprocess_workflow_files')
      && stable(next.subprocess_workflow_files) !== stable(next.workflow_nodes)) {
      throw new Error('Conflicting workflow_nodes and subprocess_workflow_files');
    }
    next.subprocess_workflow_files = next.workflow_nodes;
    delete next.workflow_nodes;
  }
  for (const ref of next.subprocess_workflow_files || []) {
    if (ref && typeof ref === 'object' && Object.hasOwn(ref, 'workflow_name')) {
      if (Object.hasOwn(ref, 'name') && ref.name !== ref.workflow_name) throw new Error('Conflicting subprocess file names');
      ref.name = ref.workflow_name;
      delete ref.workflow_name;
    }
  }
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
