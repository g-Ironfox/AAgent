import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { createNode, portsForNode, setNodeStructs } from './static/workflow/domain/node-contract.js';
import { isValidConnection } from './static/workflow/domain/connection-rules.js';
import { loadSnapshot, state, workflowSnapshot } from './static/workflow/domain/serialization.js';
import { bindStructureInspector } from './static/workflow/inspector/structure.js';
import { remapStructReferences } from './static/workflow/domain/struct-editing.js';

const task = { id: 'task', name: 'Task', color: '#123456', list_color: '#654321', fields: [{ name: 'name', type: 'content', required: true }] };
const control = (fromId, toId) => ({ id: `${fromId}-${toId}`, fromId, fromPortId: 'control-out', toId, toPortId: 'control-in', type: 'control' });
const data = (fromId, fromPortId, toId, toPortId, type) => ({ id: `${fromId}-${toId}-data`, fromId, fromPortId, toId, toPortId, type });
function fixture(valueType = 'list-content') {
  const struct = valueType === 'list-struct:task';
  const inputs = struct ? [] : [{ name: 'items', type: valueType }];
  const source = struct ? 'list' : 'input';
  return {
    schema_version: '2.0', name: 'list_length', metadata: { structs: [task], tools: [] },
    input_ports: inputs, output_ports: [{ name: 'length', type: 'number' }], subprocess_workflow_files: [], remote_tools: [],
    nodes: [
      { id: 'input', type: 'input', workflowPorts: inputs.map((port) => ({ ...port, id: `workflow:${port.name}` })) },
      ...(struct ? [{ id: 'list', type: 'construct_list', arguments: { item_type: 'struct:task', initial_value_count: 0 }, dataInputPorts: [] }] : []),
      { id: 'length', type: 'list_length', arguments: { value_type: valueType } },
      { id: 'output', type: 'output', workflowPorts: [{ id: 'workflow:length', name: 'length', type: 'number' }] },
    ],
    connections: [
      ...(struct ? [control('input', 'list')] : []), control(source, 'length'), control('length', 'output'),
      data(source, struct ? 'list-out' : 'workflow:items', 'length', 'list-in', valueType),
      data('length', 'length-out', 'output', 'workflow:length', 'number'),
    ],
  };
}

test('list_length exposes a typed list input and a numeric length output', () => {
  const node = createNode('list_length', []);
  assert.equal(node.value_type, 'list-content');
  assert.deepEqual(portsForNode(node).map(({ id, type }) => ({ id, type })), [
    { id: 'control-in', type: 'control' }, { id: 'list-in', type: 'list-content' },
    { id: 'control-out', type: 'control' }, { id: 'length-out', type: 'number' },
  ]);
  setNodeStructs([node], [task]);
  node.value_type = 'list-struct:task';
  assert.equal(portsForNode(node).find((port) => port.id === 'list-in').color, task.list_color);
  assert.equal(portsForNode(node).find((port) => port.id === 'length-out').type, 'number');
});

test('all list types save and reload with valid connections accepted by the runtime backend', () => {
  const valid = [];
  for (const valueType of ['list-content', 'list-message', 'list-struct:task']) {
    assert.equal(loadSnapshot(fixture(valueType)), true, valueType);
    assert.equal(state.connections.every((edge) => isValidConnection(edge, state.nodes)), true);
    const saved = workflowSnapshot();
    assert.deepEqual(saved.nodes.find((node) => node.id === 'length').arguments, { value_type: valueType });
    assert.equal(loadSnapshot(saved), true);
    assert.deepEqual(workflowSnapshot(), saved);
    valid.push(saved);
  }
  const invalid = [];
  for (const valueType of ['content', 'number', 'list-number', 'list-struct:missing', null, '']) {
    const workflow = fixture();
    workflow.nodes[1].arguments.value_type = valueType;
    assert.equal(loadSnapshot(workflow), false, String(valueType));
    invalid.push(workflow);
  }
  for (const args of [undefined, {}, { value_type: 'list-content', position: 'end' }]) {
    const workflow = fixture();
    workflow.nodes[1].arguments = args;
    assert.equal(loadSnapshot(workflow), false);
    invalid.push(workflow);
  }
  for (const [port, type] of [['list-in', 'list-message'], ['workflow:length', 'content']]) {
    const workflow = fixture();
    workflow.connections.find((edge) => edge.toPortId === port).type = type;
    invalid.push(workflow);
  }
  const script = `import json, sys
sys.path.insert(0, sys.argv[1])
from workflow_validator import WorkflowValidationError, validate_workflow
cases = json.load(sys.stdin)
for workflow in cases["valid"]: validate_workflow(workflow)
for workflow in cases["invalid"]:
    try: validate_workflow(workflow)
    except WorkflowValidationError: pass
    else: raise AssertionError("invalid list_length accepted")`;
  const backend = 'agent_runtime';
  const result = spawnSync(process.env.PYTHON || 'python', ['-c', script, backend], {
    cwd: fileURLToPath(new URL('..', import.meta.url)), input: JSON.stringify({ valid, invalid }), encoding: 'utf8', timeout: 30000,
  });
  assert.ifError(result.error);
  assert.equal(result.status, 0, `${backend}: ${result.stderr}`);
});

test('list type selection offers only supported lists and reconciles incompatible inputs', () => {
  assert.equal(loadSnapshot(fixture()), true);
  const node = state.nodes.find((item) => item.id === 'length');
  const field = { value: '', handlers: {}, options: [], addEventListener(event, callback) { this.handlers[event] = callback; },
    add(option) { this.options.push(option); option.remove = () => { this.options = this.options.filter((item) => item !== option); }; } };
  const previousOption = globalThis.Option;
  globalThis.Option = class { constructor(text, value) { this.text = text; this.value = value; } };
  try {
    for (const type of ['list-content', 'list-message']) field.add(new Option(type, type));
    let changes = 0;
    const context = { elements: { inspectorContent: { querySelector: () => field } }, markChanged() { changes += 1; }, editor: { renderNodes() {} }, renderInspector() {} };
    bindStructureInspector(node, context);
    assert.deepEqual(field.options.map((option) => option.value), ['list-content', 'list-message', 'list-struct:task']);
    assert.equal(field.value, 'list-content');
    field.value = 'list-message';
    field.handlers.change();
    assert.equal(node.value_type, 'list-message');
    assert.equal(state.connections.some((edge) => edge.toPortId === 'list-in'), false);
    assert.equal(state.connections.some((edge) => edge.fromPortId === 'length-out'), true);
    assert.equal(changes, 1);
  } finally { globalThis.Option = previousOption; }
});

test('renaming a Struct keeps list_length type references and connections', () => {
  const workflow = fixture('list-struct:task');
  workflow.metadata.structs = [{ ...task, id: 'renamed', name: 'Renamed' }];
  remapStructReferences(workflow, new Map([['task', 'renamed']]));
  assert.equal(loadSnapshot(workflow), true);
  assert.equal(state.nodes.find((node) => node.id === 'length').value_type, 'list-struct:renamed');
  assert.equal(state.connections.length, workflow.connections.length);
});

test('the node library and inspector expose list_length with an input list type selector', () => {
  const html = readFileSync(new URL('./static/workflow_edit.html', import.meta.url), 'utf8');
  assert.match(html, /data-add-node="list_length"/);
  const template = html.match(/<template id="list_lengthInspectorTemplate">([\s\S]*?)<\/template>/)[1];
  assert.match(template, /data-field="value_type"/);
  assert.match(template, /value="list-content"/);
  assert.match(template, /value="list-message"/);
  assert.doesNotMatch(template, /<p\b[^>]*class="field-hint"/);
});
