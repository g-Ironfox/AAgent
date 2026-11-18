import assert from 'node:assert/strict';
import test from 'node:test';
import { createNode, NODE_TYPES, portsForNode } from './static/workflow/domain/node-contract.js';
import { isValidConnection } from './static/workflow/domain/connection-rules.js';
import { loadSnapshot, workflowSnapshot } from './static/workflow/domain/serialization.js';

test('output_to_terminal is a serializable builtin with typed content and control ports', () => {
  assert.equal(NODE_TYPES.has('output_to_terminal'), true);
  const input = { id: 'input', type: 'input', workflowPorts: [{ id: 'workflow:text', name: 'text', type: 'content' }] };
  const node = createNode('output_to_terminal', [input], { x: 100, y: 100 });
  const output = { id: 'output', type: 'output', workflowPorts: [] };
  const ports = portsForNode(node);
  assert.equal(ports.find((port) => port.id === 'content-in').label, 'content');
  assert.equal(ports.find((port) => port.id === 'content-in').type, 'content');
  assert.deepEqual(ports.filter((port) => port.type === 'control').map((port) => port.id), ['control-in', 'control-out']);
  const nodes = [input, node, output];
  const edges = [
    { id: 'control-in', fromId: 'input', fromPortId: 'control-out', toId: node.id, toPortId: 'control-in', type: 'control' },
    { id: 'control-out', fromId: node.id, fromPortId: 'control-out', toId: 'output', toPortId: 'control-in', type: 'control' },
    { id: 'text', fromId: 'input', fromPortId: 'workflow:text', toId: node.id, toPortId: 'content-in', type: 'content' },
  ];
  assert.equal(edges.every((edge) => isValidConnection(edge, nodes)), true);
  const document = {
    schema_version: '2.0', name: 'terminal_output', input_ports: [{ name: 'text', type: 'content' }],
    output_ports: [], nodes, connections: edges, metadata: { structs: [] }, subprocess_workflow_files: [], remote_tools: [],
  };
  assert.equal(loadSnapshot(document), true);
  assert.equal(workflowSnapshot().nodes[1].type, 'output_to_terminal');
});
