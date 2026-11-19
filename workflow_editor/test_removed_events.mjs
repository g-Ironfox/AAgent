import assert from 'node:assert/strict';
import { test } from 'node:test';
import { readFileSync } from 'node:fs';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { loadSnapshot, resetWorkflow, workflowSnapshot } from './static/workflow/domain/serialization.js';

function fixture() {
  return {
    schema_version: '2.0', name: 'typed-process', metadata: { structs: [], tools: [] },
    input_ports: [{ name: 'origin', type: 'content' }],
    output_ports: [{ name: 'result', type: 'content' }],
    nodes: [
      { id: 'input', type: 'input', workflowPorts: [{ id: 'workflow:origin', name: 'origin', type: 'content' }] },
      { id: 'output', type: 'output', workflowPorts: [{ id: 'workflow:result', name: 'result', type: 'content' }] },
    ],
    connections: [
      { id: 'control', fromId: 'input', fromPortId: 'control-out', toId: 'output', toPortId: 'control-in', type: 'control' },
      { id: 'value', fromId: 'input', fromPortId: 'workflow:origin', toId: 'output', toPortId: 'workflow:result', type: 'content' },
    ],
  };
}
function withNode(type, args) {
  const doc = fixture();
  doc.nodes.splice(1, 0, { id: 'operation', type, arguments: args });
  doc.connections[0].toId = 'operation';
  doc.connections.push({ id: 'next', fromId: 'operation', fromPortId: 'control-out', toId: 'output', toPortId: 'control-in', type: 'control' });
  return doc;
}
const obsolete = [];
for (const type of ['split_event', 'construct_event', 'publish_event', 'history']) {
  obsolete.push([type, withNode(type, {})]);
}
for (const type of ['event', 'list-event']) {
  let doc = fixture();
  doc.input_ports[0].type = type;
  doc.nodes[0].workflowPorts[0].type = type;
  obsolete.push([type + ' boundary', doc]);
  doc = fixture();
  doc.connections[1].type = type;
  obsolete.push([type + ' connection', doc]);
  doc = fixture();
  doc.subprocess_workflow_files = [{ name: 'child', input_ports: [{ name: 'value', type }], output_ports: [] }];
  obsolete.push([type + ' child declaration', doc]);
  doc = fixture();
  doc.remote_tools = [{ name: 'remote', input_ports: [], output_ports: [{ name: 'value', type }] }];
  obsolete.push([type + ' legacy Tool declaration', doc]);
  doc = fixture();
  doc.metadata.structs = [{ id: 'Record', name: 'Record', color: '#123456', fields: [{ name: 'value', type, required: true }] }];
  obsolete.push([type + ' Struct field', doc]);
  doc = fixture();
  doc.metadata.tools = [{ name: 'remote', kind: 'remote', input_ports: [{ name: 'value', type }], output_ports: [] }];
  obsolete.push([type + ' Tool interface', doc]);
  for (const nodeType of ['context_create', 'context_read', 'context_write', 'session_create', 'session_read', 'session_write']) {
    obsolete.push([type + ' ' + nodeType, withNode(nodeType, { value_type: type })]);
  }
  obsolete.push([type + ' JSON output', withNode('deserialize_json', { outputs: [{ key: 'value', type }] })]);
}
for (const type of ['construct_list', 'list_append', 'foreach']) {
  obsolete.push([type + ' event items', withNode(type, { item_type: 'event', ...(type === 'construct_list' ? { initial_value_count: 0 } : {}), ...(type === 'list_append' ? { position: 'end' } : {}) })]);
}
obsolete.push(['while_pop event list', withNode('while_pop', { value_type: 'list-event' })]);

test('new workflows have no implicit event input and accept an ordinary content origin', () => {
  assert.equal(resetWorkflow(), true);
  assert.deepEqual(workflowSnapshot().input_ports, []);
  assert.equal(loadSnapshot(fixture()), true);
  assert.deepEqual(workflowSnapshot().input_ports, fixture().input_ports);
});

test('editor rejects removed event nodes and types without modifying the current document', () => {
  assert.equal(loadSnapshot(fixture()), true);
  const before = workflowSnapshot();
  const warn = console.warn;
  console.warn = () => {};
  try {
    for (const [name, doc] of obsolete) {
      assert.equal(loadSnapshot(doc), false, name);
      assert.deepEqual(workflowSnapshot(), before, name + ' changed editor state');
    }
  } finally { console.warn = warn; }
});

test('Agent and Manager reject the same obsolete workflows and keep content interfaces valid', () => {
  const script = [
    'import json,sys',
    'from workflow_validator import validate_workflow, WorkflowValidationError',
    'workflows=json.load(sys.stdin)',
    'validate_workflow(workflows[0])',
    'for name,workflow in workflows[1:]:',
    '    try: validate_workflow(workflow)',
    '    except WorkflowValidationError: continue',
    '    raise AssertionError(name)',
  ].join('\n');
  for (const backend of ['agent', 'manager_webui']) {
    const result = spawnSync('python', ['-c', script], {
      cwd: fileURLToPath(new URL('../' + backend + '/', import.meta.url)),
      input: JSON.stringify([fixture(), ...obsolete]), encoding: 'utf8',
    });
    assert.equal(result.status, 0, backend + ': ' + result.stdout + result.stderr);
  }
});

test('published Workflow 2.0 schemas match the validator copies', () => {
  const schemas = ['docs/protocol', 'agent', 'manager_webui'].map((dir) => JSON.parse(readFileSync(new URL('../' + dir + '/workflow_2_0.schema.json', import.meta.url), 'utf8')));
  assert.deepEqual(schemas[0], schemas[1]);
  assert.deepEqual(schemas[0], schemas[2]);
});
