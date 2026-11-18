import assert from 'node:assert/strict';
import { test } from 'node:test';
import { createNode, NODE_TYPES, portsForNode } from './static/workflow/domain/node-contract.js';
import { loadSnapshot, parseWorkflowText, workflowSnapshot, migrateSubprocessWorkflowFormat } from './static/workflow/domain/serialization.js';
import { parseWorkflowFile, editWorkflowMetadata, migrateSubprocessWorkflowFormat as migrateWorkspace } from '../webui_py/static/workflow-file.mjs';

const ports = [{ name: 'text', type: 'content' }];
function legacy() {
  return {
    schema_version: '2.0', name: 'parent', metadata: { structs: [] }, input_ports: ports, output_ports: ports,
    workflow_nodes: [{ name: 'child.flow', input_ports: ports, output_ports: ports }],
    nodes: [
      { id: 'input', type: 'input' },
      { id: 'call', type: 'workflow', name: 'Run child', x: 250, y: 100, arguments: { workflow_name: 'child.flow' }, input_ports: ports, output_ports: ports },
      { id: 'output', type: 'output' },
    ],
    connections: [
      { fromId: 'input', fromPortId: 'control-out', toId: 'call', toPortId: 'control-in', type: 'control' },
      { fromId: 'call', fromPortId: 'control-out', toId: 'output', toPortId: 'control-in', type: 'control' },
      { fromId: 'input', fromPortId: 'workflow:text', toId: 'call', toPortId: 'workflow:text', type: 'content' },
      { fromId: 'call', fromPortId: 'workflow:text', toId: 'output', toPortId: 'workflow:text', type: 'content' },
    ],
  };
}

test('old Workflow imports export only subprocess files and spawn-and-wait nodes', () => {
  const source = legacy();
  const before = structuredClone(source);
  const migrated = parseWorkflowText(JSON.stringify(source));
  assert.equal(loadSnapshot(migrated), true);
  const snapshot = workflowSnapshot();
  assert.equal('workflow_nodes' in snapshot, false);
  assert.deepEqual(snapshot.subprocess_workflow_files, source.workflow_nodes);
  assert.equal(snapshot.nodes[1].type, 'spawn_and_wait_subprocess');
  assert.deepEqual(snapshot.nodes[1].arguments, { workflow_file: 'child.flow' });
  assert.equal(snapshot.nodes[1].id, 'call');
  assert.equal(snapshot.nodes[1].x, 250);
  assert.equal(snapshot.nodes[1].name, 'Run child');
  assert.deepEqual(snapshot.connections.map(({ id, ...edge }) => edge), source.connections);
  assert.deepEqual(source, before);
  assert.equal(loadSnapshot(snapshot), true);
  assert.deepEqual(workflowSnapshot(), snapshot);
});

test('the subprocess action exposes the file contract and continues after exit', () => {
  assert.equal(NODE_TYPES.has('workflow'), false);
  const node = createNode('spawn_and_wait_subprocess', [], { name: 'child.flow', input_ports: ports, output_ports: ports });
  assert.match(node.name, /拉起并等待子进程/);
  assert.equal(node.workflow_file, 'child.flow');
  assert.deepEqual(portsForNode(node).map((port) => port.id), ['control-in', 'workflow:text', 'control-out', 'workflow:text']);
  assert.match(portsForNode(node).find((port) => port.id === 'control-out').title, /子进程退出/);
});

test('workspace editing migrates old references and remaps just the target file', () => {
  const source = legacy();
  const parsed = parseWorkflowFile(JSON.stringify(source));
  assert.equal(parsed.nodes[1].type, 'spawn_and_wait_subprocess');
  const edited = editWorkflowMetadata(source, { name: 'parent', description: '', subprocessFiles: ['new.flow'] });
  assert.equal(edited.nodes[1].arguments.workflow_file, 'new.flow');
  assert.equal(edited.subprocess_workflow_files[0].name, 'new.flow');
  assert.deepEqual(edited.connections, source.connections);
  assert.equal('workflow_nodes' in edited, false);
});

test('editor and workspace reject conflicting legacy/new references and targets', () => {
  for (const migrate of [migrateSubprocessWorkflowFormat, migrateWorkspace]) {
    const root = legacy(); root.subprocess_workflow_files = [];
    assert.throws(() => migrate(root), /Conflicting/);
    const node = legacy(); node.nodes[1].arguments.workflow_file = 'other.flow';
    assert.throws(() => migrate(node), /Conflicting/);
    assert.deepEqual(migrate(migrate(legacy())), migrate(legacy()));
    const equal = legacy();
    equal.subprocess_workflow_files = [{ output_ports: ports, input_ports: ports, name: "child.flow" }];
    assert.doesNotThrow(() => migrate(equal));
  }
});
