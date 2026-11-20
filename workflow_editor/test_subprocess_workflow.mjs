import assert from 'node:assert/strict';
import { test } from 'node:test';
import { readFile } from 'node:fs/promises';
import { createNode, NODE_TYPES, portsForNode } from './static/workflow/domain/node-contract.js';
import { loadSnapshot, parseWorkflowText, workflowSnapshot, migrateSubprocessWorkflowFormat } from './static/workflow/domain/serialization.js';
import { parseWorkflowFile, editWorkflowMetadata, migrateSubprocessWorkflowFormat as migrateWorkspace } from '../webui_py/static/workflow-file.mjs';
import { workflowCanvasSvg } from '../webui_py/static/workflow_canvas.mjs';

function workflow() {
  return {
    schema_version: '2.0', metadata: { structs: [] },
    input_ports: [{ name: 'file', type: 'content' }, { name: 'arguments', type: 'content' }],
    output_ports: [{ name: 'result', type: 'content' }],
    nodes: [{ id: 'input', type: 'input' }, { id: 'call', type: 'spawn_and_wait_subprocess', name: 'Run child', arguments: {} }, { id: 'output', type: 'output' }],
    connections: [
      { fromId: 'input', fromPortId: 'control-out', toId: 'call', toPortId: 'control-in', type: 'control' },
      { fromId: 'call', fromPortId: 'control-out', toId: 'output', toPortId: 'control-in', type: 'control' },
      { fromId: 'input', fromPortId: 'workflow:file', toId: 'call', toPortId: 'workflow-file', type: 'content' },
      { fromId: 'input', fromPortId: 'workflow:arguments', toId: 'call', toPortId: 'arguments-json', type: 'content' },
      { fromId: 'call', fromPortId: 'result-json', toId: 'output', toPortId: 'workflow:result', type: 'content' },
    ],
  };
}

test('standalone subprocess node needs no declaration or configuration', () => {
  assert.equal(NODE_TYPES.has('spawn_and_wait_subprocess'), true);
  const node = createNode('spawn_and_wait_subprocess', []);
  assert.ok(node);
  assert.equal('workflow_file' in node, false);
  assert.deepEqual(portsForNode(node).map(({ id, direction, type }) => [id, direction, type]), [
    ['control-in', 'input', 'control'], ['workflow-file', 'input', 'content'], ['arguments-json', 'input', 'content'],
    ['control-out', 'output', 'control'], ['result-json', 'output', 'content'],
  ]);
});

test('JSON call graphs round-trip without declarations or interface snapshots', () => {
  const source = workflow();
  const before = structuredClone(source);
  assert.equal(loadSnapshot(parseWorkflowText(JSON.stringify(source))), true);
  const saved = workflowSnapshot();
  assert.equal('subprocess_workflow_files' in saved, false);
  assert.equal('workflow_nodes' in saved, false);
  assert.deepEqual(saved.nodes[1].arguments, {});
  assert.equal('input_ports' in saved.nodes[1], false);
  assert.equal('output_ports' in saved.nodes[1], false);
  assert.deepEqual(saved.connections, source.connections);
  assert.deepEqual(source, before);
  assert.equal(parseWorkflowFile(JSON.stringify(saved)).schema_version, '2.0');
});

test('editor and workspace discard obsolete declarations without mutating documents', () => {
  for (const migrate of [migrateSubprocessWorkflowFormat, migrateWorkspace]) {
    const source = { ...workflow(), name: 'old', workflow_nodes: [{ name: 'a.flow' }], subprocess_workflow_files: [{ name: 'b.flow' }] };
    source.metadata.name = 'old';
    const before = structuredClone(source);
    const saved = migrate(source);
    assert.equal('workflow_nodes' in saved, false);
    assert.equal('subprocess_workflow_files' in saved, false);
    assert.equal('name' in saved, false);
    assert.equal('name' in saved.metadata, false);
    assert.deepEqual(source, before);
    assert.deepEqual(migrate(saved), saved);
  }
});

test('old fixed interface calls require explicit reconnection instead of silently dropping data', () => {
  for (const extra of [{ arguments: { workflow_file: 'child.flow' } }, { input_ports: [] }, { output_ports: [] }]) {
    const source = workflow();
    Object.assign(source.nodes[1], extra);
    assert.equal(loadSnapshot(source), false);
  }
});

test('metadata edits preserve JSON call wiring and node settings', () => {
  const source = workflow();
  const edited = editWorkflowMetadata(source, { description: 'new' });
  assert.equal(edited.description, 'new');
  assert.deepEqual(edited.nodes, source.nodes);
  assert.deepEqual(edited.connections, source.connections);
  assert.equal('subprocess_workflow_files' in edited, false);
  assert.match(workflowCanvasSvg(edited, 'parent.flow'), /workflow-file/);
});

test('editor has one standalone library button and no subprocess metadata controls', async () => {
  const html = await readFile(new URL('./static/workflow_edit.html', import.meta.url), 'utf8');
  assert.match(html, /data-add-node="spawn_and_wait_subprocess"/);
  assert.doesNotMatch(html, /subprocessWorkflowFileList|subprocessWorkflowFileTemplate|addSubprocessWorkflowFileButton|data-workflow-file/);
});
