import assert from 'node:assert/strict';
import test from 'node:test';
import { createNode, NODE_TYPES, portsForNode } from './static/workflow/domain/node-contract.js';
import { isValidConnection } from './static/workflow/domain/connection-rules.js';
import { loadSnapshot, workflowSnapshot } from './static/workflow/domain/serialization.js';

test('read_terminal_input exposes a list-content output', () => {
  assert.equal(NODE_TYPES.has('read_terminal_input'), true);
  const node = createNode('read_terminal_input', [], { x: 100, y: 100 });
  assert.deepEqual(portsForNode(node).map(({ id, type }) => ({ id, type })), [
    { id: 'control-in', type: 'control' },
    { id: 'control-out', type: 'control' },
    { id: 'list-out', type: 'list-content' },
  ]);
});

test('wait_terminal_event preserves control flow and round-trips without arguments or data ports', () => {
  assert.equal(NODE_TYPES.has('wait_terminal_event'), true);
  const input = { id: 'input', type: 'input', workflowPorts: [] };
  const wait = createNode('wait_terminal_event', [input], { x: 100, y: 100 });
  const output = { id: 'output', type: 'output', workflowPorts: [] };
  assert.deepEqual(portsForNode(wait).map(({ id, type }) => ({ id, type })), [
    { id: 'control-in', type: 'control' },
    { id: 'control-out', type: 'control' },
  ]);
  const nodes = [input, wait, output];
  const connections = [
    { id: 'enter', fromId: 'input', fromPortId: 'control-out', toId: wait.id, toPortId: 'control-in', type: 'control' },
    { id: 'continue', fromId: wait.id, fromPortId: 'control-out', toId: 'output', toPortId: 'control-in', type: 'control' },
  ];
  assert.equal(connections.every((edge) => isValidConnection(edge, nodes)), true);
  assert.equal(loadSnapshot({ schema_version: '2.0', name: 'wait', input_ports: [], output_ports: [],
    nodes, connections, metadata: { structs: [] }, subprocess_workflow_files: [], remote_tools: [] }), true);
  const snapshot = workflowSnapshot();
  assert.equal(snapshot.nodes[1].type, 'wait_terminal_event');
  assert.equal(JSON.stringify(snapshot.nodes[1].arguments || {}), '{}');
  assert.equal(snapshot.connections.length, 2);
});
