import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { createNode, portsForNode } from './static/workflow/domain/node-contract.js';
import { isValidConnection } from './static/workflow/domain/connection-rules.js';
import { loadSnapshot, state, workflowSnapshot } from './static/workflow/domain/serialization.js';

function fixture(valueType = 'list-content') {
  const workflow = {
    schema_version: '2.0', name: 'list_slice', metadata: { structs: [], tools: [] },
    input_ports: [{ name: 'items', type: valueType }], output_ports: [{ name: 'items', type: valueType }],
    workflow_nodes: [], remote_tools: [],
    nodes: [
      { id: 'input', type: 'input', workflowPorts: [{ id: 'workflow:items', name: 'items', type: valueType }] },
      { id: 'slice', type: 'list_slice', arguments: { value_type: valueType } },
      { id: 'output', type: 'output', workflowPorts: [{ id: 'workflow:items', name: 'items', type: valueType }] },
    ],
    connections: [
      { id: 'run-slice', fromId: 'input', fromPortId: 'control-out', toId: 'slice', toPortId: 'control-in', type: 'control' },
      { id: 'items-in', fromId: 'input', fromPortId: 'workflow:items', toId: 'slice', toPortId: 'list-in', type: valueType },
      { id: 'run-output', fromId: 'slice', fromPortId: 'control-out', toId: 'output', toPortId: 'control-in', type: 'control' },
      { id: 'items-out', fromId: 'slice', fromPortId: 'list-out', toId: 'output', toPortId: 'workflow:items', type: valueType },
    ],
  };
  return workflow;
}

test('list_slice ports preserve the selected list type and expose optional numeric bounds', () => {
  const node = createNode('list_slice', []);
  assert.equal(node.value_type, 'list-content');
  assert.deepEqual(portsForNode(node).map(({ id, type }) => [id, type]), [
    ['control-in', 'control'], ['list-in', 'list-content'], ['start-in', 'number'], ['stop-in', 'number'], ['step-in', 'number'],
    ['control-out', 'control'], ['list-out', 'list-content'],
  ]);
  for (const valueType of ['list-content', 'list-message']) {
    node.value_type = valueType;
    assert.equal(portsForNode(node).find((port) => port.id === 'list-out').type, valueType);
  }
});

test('typed list_slice snapshots survive save and reload and validate in both backends', () => {
  const valid = [];
  for (const valueType of ['list-content', 'list-message']) {
    const workflow = fixture(valueType);
    assert.equal(loadSnapshot(workflow), true);
    assert.equal(state.connections.every((edge) => isValidConnection(edge, state.nodes)), true);
    const saved = workflowSnapshot();
    assert.deepEqual(saved.nodes.find((node) => node.id === 'slice').arguments, { value_type: valueType });
    assert.equal(loadSnapshot(saved), true);
    assert.deepEqual(workflowSnapshot(), saved);
    valid.push(saved);
  }
  const invalid = [];
  for (const valueType of ['content', 'number', 'list-number', 'list-struct:missing']) {
    const workflow = fixture();
    workflow.nodes.find((node) => node.id === 'slice').arguments.value_type = valueType;
    assert.equal(loadSnapshot(workflow), false);
    invalid.push(workflow);
  }
  const script = `import json, sys
sys.path.insert(0, sys.argv[1])
from workflow_validator import WorkflowValidationError, validate_workflow
cases = json.load(sys.stdin)
for workflow in cases["valid"]: validate_workflow(workflow)
for workflow in cases["invalid"]:
    try: validate_workflow(workflow)
    except WorkflowValidationError: continue
    raise AssertionError("invalid list_slice accepted")`;
  for (const backend of ['agent', 'manager_webui']) {
    const result = spawnSync(process.env.PYTHON || 'python', ['-c', script, backend], {
      cwd: fileURLToPath(new URL('..', import.meta.url)), input: JSON.stringify({ valid, invalid }), encoding: 'utf8', timeout: 30000,
    });
    assert.ifError(result.error);
    assert.equal(result.status, 0, `${backend}: ${result.stderr}`);
  }
});

test('list_slice is available in the node library and canvas contracts', () => {
  const html = readFileSync(new URL('./static/workflow_edit.html', import.meta.url), 'utf8');
  assert.match(html, /data-add-node="list_slice"/);
  assert.match(html, /id="list_sliceInspectorTemplate"/);
  assert.match(html, /value="list-message"/);
});
