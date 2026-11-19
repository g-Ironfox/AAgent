import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { spawnSync } from 'node:child_process';
import test from 'node:test';
import { fileURLToPath } from 'node:url';
import { boundaryPorts, createNode, portsForNode } from './static/workflow/domain/node-contract.js';
import { isValidConnection } from './static/workflow/domain/connection-rules.js';
import { loadSnapshot, state, workflowSnapshot } from './static/workflow/domain/serialization.js';

function fixture() {
  const input = [{ name: 'value', type: 'number' }];
  const output = [{ name: 'text', type: 'content' }];
  return {
    schema_version: '2.0', name: 'number_to_content',
    input_ports: input, output_ports: output,
    metadata: { structs: [] }, subprocess_workflow_files: [], remote_tools: [],
    nodes: [
      { id: 'input', type: 'input', workflowPorts: boundaryPorts(input) },
      { id: 'convert', type: 'number_to_content', arguments: {} },
      { id: 'output', type: 'output', workflowPorts: boundaryPorts(output) },
    ],
    connections: [
      { id: 'in-control', fromId: 'input', fromPortId: 'control-out', toId: 'convert', toPortId: 'control-in', type: 'control' },
      { id: 'in-data', fromId: 'input', fromPortId: 'workflow:value', toId: 'convert', toPortId: 'number-in', type: 'number' },
      { id: 'out-control', fromId: 'convert', fromPortId: 'control-out', toId: 'output', toPortId: 'control-in', type: 'control' },
      { id: 'out-data', fromId: 'convert', fromPortId: 'content-out', toId: 'output', toPortId: 'workflow:text', type: 'content' },
    ],
  };
}

test('number_to_content is created with fixed number and content ports', () => {
  const node = createNode('number_to_content', []);
  assert.equal(node.type, 'number_to_content');
  assert.match(node.name, /数字转文本/);
  assert.deepEqual(portsForNode(node).map(({ id, type, direction, multiple }) => ({ id, type, direction, multiple })), [
    { id: 'control-in', type: 'control', direction: 'input', multiple: false },
    { id: 'number-in', type: 'number', direction: 'input', multiple: false },
    { id: 'control-out', type: 'control', direction: 'output', multiple: false },
    { id: 'content-out', type: 'content', direction: 'output', multiple: true },
  ]);
});

test('conversion connections and empty arguments survive save/reload and backend validation', () => {
  assert.equal(loadSnapshot(fixture()), true);
  assert.equal(state.connections.length, 4);
  assert.ok(state.connections.every((edge) => isValidConnection(edge, state.nodes)));
  const saved = workflowSnapshot();
  assert.deepEqual(saved.nodes.find((node) => node.id === 'convert').arguments, {});
  assert.equal(loadSnapshot(saved), true);
  assert.deepEqual(workflowSnapshot(), saved);
  const result = spawnSync(process.env.PYTHON || 'python', ['-c',
    'import json, sys; sys.path.insert(0, "agent"); from workflow_validator import validate_workflow; validate_workflow(json.load(sys.stdin))'], {
    cwd: fileURLToPath(new URL('..', import.meta.url)), input: JSON.stringify(saved), encoding: 'utf8', timeout: 30000,
  });
  assert.ifError(result.error);
  assert.equal(result.status, 0, result.stderr);
});

test('conversion rejects incompatible connection types and configuration', () => {
  const workflow = fixture();
  for (const index of [1, 3]) {
    const edge = { ...workflow.connections[index], type: index === 1 ? 'content' : 'number' };
    assert.equal(isValidConnection(edge, workflow.nodes), false);
  }
  workflow.nodes[1].arguments = { value_type: 'number' };
  assert.equal(loadSnapshot(workflow), false);
});

test('the node library and inspector expose the conversion', () => {
  const html = readFileSync(new URL('./static/workflow_edit.html', import.meta.url), 'utf8');
  assert.match(html, /data-add-node="number_to_content"/);
  const template = html.match(/<template id="number_to_contentInspectorTemplate">([\s\S]*?)<\/template>/)[1];
  assert.match(template, /data-interface-contract/);
  assert.match(template, /data-field="name"/);
  assert.match(template, /data-delete-node/);
});
