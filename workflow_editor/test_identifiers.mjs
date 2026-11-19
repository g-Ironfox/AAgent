import assert from 'node:assert/strict';
import { test } from 'node:test';
import { createNode, portsForNode } from './static/workflow/domain/node-contract.js';
import { addNode, deleteNode, loadSnapshot, state, workflowSnapshot } from './static/workflow/domain/serialization.js';
import { isValidConnection } from './static/workflow/domain/connection-rules.js';

const suffix = (node) => Number(/_(\d+)$/.exec(node.id)[1]);

test('new node IDs use their names and a monotonic suffix across deletion and import', () => {
  const doc = workflowSnapshot();
  doc.nodes[0].id = 'Imported_9000';
  doc.connections = [];
  assert.equal(loadSnapshot(doc), true);
  // Even deleting an imported maximum does not roll the counter back.
  state.nodes = state.nodes.filter((node) => node.id !== 'Imported_9000');
  const first = addNode('construct_content');
  assert.equal(first.id, `${first.name}_${suffix(first)}`);
  assert.ok(suffix(first) > 9000);
  assert.equal(deleteNode(first.id), true);
  const second = addNode('construct_content');
  assert.ok(suffix(second) > suffix(first));
  const router = createNode('router', [second]);
  assert.ok(suffix(router) > suffix(second));
  assert.equal(new Set(router.branches.map((branch) => branch.id)).size, 2);
  assert.ok(portsForNode(router).some((port) => port.id === router.branches[0].id));
});

test('connection IDs stay internal and survive undo snapshots while exports omit them', () => {
  const doc = {
    schema_version: '2.0', metadata: {}, input_ports: [], output_ports: [],
    nodes: [{ id: 'in', type: 'input' }, { id: 'wait', type: 'wait_terminal_event' }, { id: 'out', type: 'output' }],
    connections: [
      { fromId: 'in', fromPortId: 'control-out', toId: 'wait', toPortId: 'control-in', type: 'control' },
      { fromId: 'wait', fromPortId: 'control-out', toId: 'out', toPortId: 'control-in', type: 'control' },
    ],
  };
  assert.equal(loadSnapshot(doc), true);
  assert.equal(new Set(state.connections.map((edge) => edge.id)).size, 2);
  assert.ok(state.connections.every((edge) => isValidConnection(edge, state.nodes)));
  const internal = workflowSnapshot({ includeConnectionIds: true });
  const exported = workflowSnapshot();
  assert.deepEqual(exported.connections, doc.connections);
  assert.ok(state.connections.every((edge) => typeof edge.id === 'string'));
  assert.equal(loadSnapshot(internal), true);
  assert.deepEqual(workflowSnapshot({ includeConnectionIds: true }), internal);
  assert.equal(loadSnapshot(exported), true);
  assert.deepEqual(workflowSnapshot(), exported);
});
