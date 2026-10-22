import assert from 'node:assert/strict';
import { test } from 'node:test';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { prepareStructDefinitions, remapStructReferences } from './static/workflow/domain/struct-editing.js';
import { loadSnapshot, state, workflowSnapshot } from './static/workflow/domain/serialization.js';
import { isValidConnection } from './static/workflow/domain/connection-rules.js';

const definition = (id, name = id, fields = []) => ({ id, name, color: '#3A7D68', fields });
const field = (name, type) => ({ name, type, required: true });

test('user-entered Struct name becomes its ID without mutating the draft', () => {
  const draft = [definition('struct_mvjp3il2_2', 'workflow_payload', [field('content', 'content')])];
  const before = structuredClone(draft);
  const { structs, idMap } = prepareStructDefinitions(draft);
  assert.equal(structs[0].id, 'workflow_payload');
  assert.equal(structs[0].name, 'workflow_payload');
  assert.equal(idMap.get('struct_mvjp3il2_2'), 'workflow_payload');
  assert.deepEqual(draft, before);
});

test('Struct names must be identifiers and case-insensitively unique', () => {
  for (const name of ['', '123', 'two words', 'bad-name', 'a'.repeat(81)]) {
    assert.throws(() => prepareStructDefinitions([definition('old', name)]), /Struct 名称/);
  }
  assert.throws(() => prepareStructDefinitions([definition('a', 'Profile'), definition('b', 'profile')]), /不能重复/);
  assert.equal(prepareStructDefinitions([definition('old', ' _profile_1 ')]).structs[0].id, '_profile_1');
});

test('swapping names remaps nested Struct and list types exactly once', () => {
  const { structs, idMap } = prepareStructDefinitions([
    definition('A', 'B'), definition('B', 'A'),
    definition('wrapper', 'payload', [field('one', 'struct:A'), field('many', 'list-struct:B')]),
  ]);
  assert.deepEqual(structs[2].fields.map((item) => item.type), ['struct:B', 'list-struct:A']);
  const workflow = {
    nodes: [
      { id: 'keep_me', type: 'workflow', input_ports: [{ name: 'one', type: 'struct:A' }] },
      { id: 'serialized', type: 'workflow', arguments: { workflow_name: 'child' }, output_ports: [{ name: 'many', type: 'list-struct:B' }] },
      { id: 'tool', type: 'local_tool', parameters: ['struct:A'] },
      { id: 'literal', type: 'construct_content', append_items: [{ type: 'fixed', value: 'struct:A' }] },
    ],
  };
  remapStructReferences(workflow, idMap);
  assert.equal(workflow.nodes[0].input_ports[0].type, 'struct:B');
  assert.equal(workflow.nodes[1].output_ports[0].type, 'list-struct:A');
  assert.deepEqual(workflow.nodes[2].parameters, ['struct:A']);
  assert.equal(workflow.nodes[3].append_items[0].value, 'struct:A');
  assert.equal(workflow.nodes[0].id, 'keep_me');
});

test('renaming preserves connected Struct, list, JSON and Context nodes through round-trip', () => {
  const old = 'struct_mvjp3il2_2';
  const workflow = {
    schema_version: '2.0', name: 'renaming',
    metadata: { structs: [definition(old, 'Profile', [field('display_name', 'content')])] },
    input_ports: [{ name: 'text', type: 'content' }], output_ports: [],
    nodes: [
      { id: 'input', type: 'input' }, { id: 'output', type: 'output' },
      { id: 'make', type: 'construct_struct', arguments: { struct_id: old }, dataInputPorts: ['display_name'] },
      { id: 'get', type: 'struct_get', arguments: { struct_id: old, field: 'display_name', missing: 'error', has_fallback: false }, dataInputPorts: ['struct-in'] },
      { id: 'update', type: 'struct_update', arguments: { struct_id: old, updates: [], remove_fields: [] }, dataInputPorts: ['struct-in'] },
      { id: 'list', type: 'construct_list', arguments: { item_type: `struct:${old}`, initial_value_count: 1 }, dataInputPorts: [`struct:${old}-in-0`] },
      { id: 'json', type: 'struct_to_json', arguments: { value_type: `list-struct:${old}` } },
      { id: 'parse', type: 'json_to_struct', arguments: { value_type: `struct:${old}` } },
      { id: 'context', type: 'context_create', arguments: { value_type: `list-struct:${old}` } },
      { id: 'append', type: 'list_append', arguments: { item_type: `struct:${old}`, position: 'end' } },
      { id: 'each', type: 'foreach', arguments: { item_type: `struct:${old}` } },
    ],
    connections: [
      { id: 'text', fromId: 'input', fromPortId: 'workflow:text', toId: 'make', toPortId: 'display_name', type: 'content' },
      { id: 'item', fromId: 'make', fromPortId: 'struct-out', toId: 'list', toPortId: `struct:${old}-in-0`, type: `struct:${old}` },
      { id: 'get', fromId: 'make', fromPortId: 'struct-out', toId: 'get', toPortId: 'struct-in', type: `struct:${old}` },
      { id: 'update', fromId: 'make', fromPortId: 'struct-out', toId: 'update', toPortId: 'struct-in', type: `struct:${old}` },
      { id: 'json', fromId: 'list', fromPortId: 'list-out', toId: 'json', toPortId: 'value-in', type: `list-struct:${old}` },
      { id: 'context', fromId: 'list', fromPortId: 'list-out', toId: 'context', toPortId: 'initial-value', type: `list-struct:${old}` },
      { id: 'append', fromId: 'list', fromPortId: 'list-out', toId: 'append', toPortId: 'list-in', type: `list-struct:${old}` },
      { id: 'each', fromId: 'list', fromPortId: 'list-out', toId: 'each', toPortId: 'list-in', type: `list-struct:${old}` },
    ],
  };
  assert.equal(loadSnapshot(workflow), true);
  assert.equal(state.connections.length, workflow.connections.length);
  const draft = structuredClone(state.metadata.structs);
  draft[0].name = 'workflow_payload';
  const { structs, idMap } = prepareStructDefinitions(draft);
  state.metadata.structs = structs;
  remapStructReferences(state, idMap);
  assert.equal(state.nodes.find((node) => node.id === 'list').dataInputPorts[0], 'struct:workflow_payload-in-0');
  const snapshot = workflowSnapshot();
  assert.equal(loadSnapshot(snapshot), true);
  assert.equal(state.connections.length, workflow.connections.length);
  assert.ok(state.connections.every((connection) => isValidConnection(connection, state.nodes)));
  assert.equal(JSON.stringify(workflowSnapshot()).includes(old), false);
});


function structPortRoundTripWorkflow(missing, updates) {
  const connect = (fromId, fromPortId, toId, toPortId, type) => ({
    id: `${fromId}:${fromPortId}:${toId}:${toPortId}`, fromId, fromPortId, toId, toPortId, type,
  });
  const inputPorts = [{ name: 'text', type: 'content' }];
  const outputPorts = [{ name: 'result', type: 'content' }];
  const workflow = {
    schema_version: '2.0', name: `struct_ports_${missing}_${updates.length}`,
    metadata: { structs: [definition('Profile', 'Profile', [
      field('name', 'content'), { name: 'nickname', type: 'content', required: false },
    ])] },
    input_ports: inputPorts, output_ports: outputPorts,
    nodes: [
      { id: 'input', type: 'input', workflowPorts: inputPorts.map((port) => ({ id: `workflow:${port.name}`, ...port })) },
      { id: 'make', type: 'construct_struct', arguments: { struct_id: 'Profile' }, dataInputPorts: ['name', 'nickname'] },
      { id: 'update', type: 'struct_update', arguments: { struct_id: 'Profile', updates, remove_fields: [] }, dataInputPorts: ['struct-in', ...updates] },
      { id: 'get', type: 'struct_get', arguments: { struct_id: 'Profile', field: missing === 'fallback' ? 'nickname' : 'name', missing, has_fallback: missing === 'fallback' }, dataInputPorts: missing === 'fallback' ? ['struct-in', 'fallback-in'] : ['struct-in'] },
      { id: 'output', type: 'output', workflowPorts: outputPorts.map((port) => ({ id: `workflow:${port.name}`, ...port })) },
    ],
    connections: [
      connect('input', 'workflow:text', 'make', 'name', 'content'),
      connect('make', 'struct-out', 'update', 'struct-in', 'struct:Profile'),
      connect('update', 'struct-out', 'get', 'struct-in', 'struct:Profile'),
      connect('get', 'value-out', 'output', 'workflow:result', 'content'),
      ...updates.map((name) => connect('input', 'workflow:text', 'update', name, 'content')),
      ...(missing === 'fallback' ? [connect('input', 'workflow:text', 'get', 'fallback-in', 'content')] : []),
    ],
  };
  for (let index = 1; index < workflow.nodes.length; index += 1) {
    workflow.connections.push(connect(workflow.nodes[index - 1].id, 'control-out', workflow.nodes[index].id, 'control-in', 'control'));
  }
  return workflow;
}

test('Struct get and update snapshots retain port contracts accepted by both backends', () => {
  const workflows = [];
  for (const missing of ['error', 'fallback']) {
    for (const updates of [[], ['name', 'nickname']]) {
      const original = structPortRoundTripWorkflow(missing, updates);
      assert.equal(loadSnapshot(original), true);
      const snapshot = workflowSnapshot();
      for (const id of ['get', 'update']) {
        assert.deepEqual(
          snapshot.nodes.find((node) => node.id === id).dataInputPorts,
          original.nodes.find((node) => node.id === id).dataInputPorts,
          `${original.name}: ${id}`,
        );
      }
      assert.deepEqual(snapshot.connections, original.connections);
      assert.equal(loadSnapshot(snapshot), true);
      assert.deepEqual(workflowSnapshot(), snapshot);
      workflows.push(original, snapshot);
    }
  }
  // Use separate processes because the backends have identically named Python modules.
  const validationScript = `
import json
import sys
sys.path.insert(0, sys.argv[1])
from workflow_validator import validate_workflow
for workflow in json.load(sys.stdin):
    validate_workflow(workflow)
    if sys.argv[1] == "agent":
        from workflow_parser import parse_workflow
        from workflow_nodes import propagate_workflow_output, run_workflow_map
        graph = parse_workflow(workflow)
        propagate_workflow_output(graph, graph[0], "workflow:text", "Ada")
        assert run_workflow_map(graph, 0) == {"result": "Ada"}
`;
  for (const backend of ['agent', 'manager_webui']) {
    const result = spawnSync(process.env.PYTHON || 'python', ['-c', validationScript, backend], {
      cwd: fileURLToPath(new URL('..', import.meta.url)),
      input: JSON.stringify(workflows), encoding: 'utf8', timeout: 30000,
    });
    assert.ifError(result.error);
    assert.equal(result.status, 0, `${backend}: ${result.stderr}`);
  }
});
