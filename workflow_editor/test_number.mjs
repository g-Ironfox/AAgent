import assert from 'node:assert/strict';
import test from 'node:test';
import { boundaryPorts, portsForNode } from './static/workflow/domain/node-contract.js';
import { isValidConnection } from './static/workflow/domain/connection-rules.js';
import { loadSnapshot, state, workflowSnapshot } from './static/workflow/domain/serialization.js';
import { toolFromSchema } from './static/workflow/domain/tool-contract.js';

function fixture() {
  const ports = [{ name: 'value', type: 'number' }];
  return {
    schema_version: '2.0', name: 'numeric', input_ports: ports, output_ports: ports,
    metadata: { structs: [] }, subprocess_workflow_files: [], remote_tools: [],
    nodes: [
      { id: 'input', type: 'input', workflowPorts: boundaryPorts(ports) },
      { id: 'output', type: 'output', workflowPorts: boundaryPorts(ports) },
    ],
    connections: [
      { id: 'control', fromId: 'input', fromPortId: 'control-out', toId: 'output', toPortId: 'control-in', type: 'control' },
      { id: 'data', fromId: 'input', fromPortId: 'workflow:value', toId: 'output', toPortId: 'workflow:value', type: 'number' },
    ],
  };
}

test('number boundary ports and edges survive save and reload', () => {
  const workflow = fixture();
  assert.equal(isValidConnection(workflow.connections[1], workflow.nodes), true);
  assert.equal(loadSnapshot(workflow), true);
  const saved = workflowSnapshot();
  assert.deepEqual(saved.input_ports, workflow.input_ports);
  assert.equal(saved.connections[1].type, 'number');
  assert.equal(loadSnapshot(saved), true);
  assert.deepEqual(workflowSnapshot(), saved);
  const incompatible = structuredClone(workflow);
  incompatible.nodes[1].workflowPorts[0].type = 'content';
  assert.equal(isValidConnection(incompatible.connections[1], incompatible.nodes), false);
});

test('number context, session, JSON and tool types survive serialization', () => {
  for (const type of ['context_create', 'context_read', 'context_write', 'session_create', 'session_read', 'session_write', 'deserialize_json', 'tool', 'local-tool']) {
    const workflow = fixture();
    const localTool = type === 'local-tool';
    const nodeType = localTool ? 'tool' : type;
    const arguments_ = type === 'deserialize_json' ? { outputs: [{ key: 'value', type: 'number' }] }
      : nodeType === 'tool' ? { tool: 'numeric', parameters: [{ name: 'value', type: 'number' }], outputs: [{ name: 'value', type: 'number' }], mode: 'sync', timeout_ms: 10000 }
        : { value_type: 'number', ...(type.startsWith('context_') && (type.endsWith('_read') || type.endsWith('_write')) ? { context_id_source: 'port' } : {}) };
    if (nodeType === 'tool') workflow.metadata.tools = [{ name: 'numeric', kind: localTool ? 'local' : 'remote', input_ports: workflow.input_ports, output_ports: workflow.output_ports }];
    workflow.nodes.splice(1, 0, { id: 'numeric', type: nodeType, arguments: arguments_ });
    assert.equal(loadSnapshot(workflow), true, type);
    assert.ok(portsForNode(state.nodes[1]).some((port) => port.type === 'number'), type);
    const saved = workflowSnapshot();
    assert.equal(loadSnapshot(saved), true, type);
    assert.deepEqual(workflowSnapshot(), saved, type);
  }
});

test('number struct fields determine numeric ports and preserve their type', () => {
  const workflow = fixture();
  workflow.metadata.structs = [{ id: 'metric', name: 'Metric', color: '#147d78', fields: [{ name: 'value', type: 'number', required: true }] }];
  workflow.nodes.splice(1, 0, { id: 'metric', type: 'construct_struct', arguments: { struct_id: 'metric' }, dataInputPorts: ['value'] });
  assert.equal(loadSnapshot(workflow), true);
  assert.equal(portsForNode(state.nodes[1]).find((port) => port.id === 'value').type, 'number');
  const saved = workflowSnapshot();
  assert.equal(saved.metadata.structs[0].fields[0].type, 'number');
  assert.equal(loadSnapshot(saved), true);
  assert.deepEqual(workflowSnapshot(), saved);
});

test('numeric tool schemas infer number for local and remote inputs and outputs', () => {
  for (const kind of ['local', 'remote']) {
    for (const type of ['integer', 'number']) {
      const tool = toolFromSchema({ name: 'numeric', inputSchema: { properties: { value: { type } } }, outputSchema: { type } }, kind);
      assert.deepEqual(tool.input_ports, [{ name: 'value', type: 'number' }]);
      assert.deepEqual(tool.output_ports, [{ name: kind === 'local' ? 'output' : 'result', type: 'number' }]);
    }
    const tool = toolFromSchema({ name: 'numeric', inputSchema: { properties: { value: { 'x-workflow-port-type': 'number' } } } }, kind);
    assert.equal(tool.input_ports[0].type, 'number');
  }
});
