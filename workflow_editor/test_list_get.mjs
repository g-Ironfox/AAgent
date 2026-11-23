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
const data = (fromId, fromPortId, toId, toPortId, type) => ({ id: `${fromId}-${toId}-${toPortId}`, fromId, fromPortId, toId, toPortId, type });
function fixture(valueType = 'list-content') {
  const struct = valueType === 'list-struct:task';
  const itemType = valueType.slice(5);
  const inputs = [{ name: 'items', type: struct ? 'content' : valueType }, { name: 'index', type: 'number' }];
  const outputType = struct ? 'content' : itemType;
  const source = struct ? 'decode' : 'input';
  return {
    schema_version: '2.0', name: 'list_get', metadata: { structs: [task], tools: [] },
    input_ports: inputs, output_ports: [{ name: 'result', type: outputType }], subprocess_workflow_files: [], remote_tools: [],
    nodes: [
      { id: 'input', type: 'input', workflowPorts: inputs.map((port) => ({ ...port, id: `workflow:${port.name}` })) },
      ...(struct ? [{ id: 'decode', type: 'json_to_struct', arguments: { value_type: valueType }, dataInputPorts: ['content-in'] }] : []),
      { id: 'get', type: 'list_get', arguments: { value_type: valueType } },
      ...(struct ? [{ id: 'encode', type: 'struct_to_json', arguments: { value_type: itemType }, dataInputPorts: ['value-in'] }] : []),
      { id: 'output', type: 'output', workflowPorts: [{ id: 'workflow:result', name: 'result', type: outputType }] },
    ],
    connections: [
      ...(struct ? [control('input', 'decode'), data('input', 'workflow:items', 'decode', 'content-in', 'content')] : []),
      control(source, 'get'),
      data(source, struct ? 'value-out' : 'workflow:items', 'get', 'list-in', valueType),
      data('input', 'workflow:index', 'get', 'index-in', 'number'),
      ...(struct ? [control('get', 'encode'), data('get', 'item-out', 'encode', 'value-in', itemType)] : []),
      control(struct ? 'encode' : 'get', 'output'),
      data(struct ? 'encode' : 'get', struct ? 'content-out' : 'item-out', 'output', 'workflow:result', outputType),
    ],
  };
}

test('list_get declares a numeric index input and an output matching the selected list', () => {
  const node = createNode('list_get', []);
  assert.equal(node.value_type, 'list-content');
  assert.deepEqual(portsForNode(node).map(({ id, type }) => ({ id, type })), [
    { id: 'control-in', type: 'control' }, { id: 'list-in', type: 'list-content' },
    { id: 'index-in', type: 'number' }, { id: 'control-out', type: 'control' }, { id: 'item-out', type: 'content' },
  ]);
  setNodeStructs([node], [task]);
  for (const valueType of ['list-content', 'list-message', 'list-struct:task']) {
    node.value_type = valueType;
    const ports = portsForNode(node);
    assert.equal(ports.find((port) => port.id === 'item-out').type, valueType.slice(5));
    assert.equal(ports.find((port) => port.id === 'index-in').type, 'number');
  }
  assert.equal(portsForNode(node).find((port) => port.id === 'list-in').color, task.list_color);
  assert.equal(portsForNode(node).find((port) => port.id === 'item-out').color, task.color);
});

test('all typed lookup snapshots survive reload and both backends validate and execute them', () => {
  const valid = [];
  for (const valueType of ['list-content', 'list-message', 'list-struct:task']) {
    assert.equal(loadSnapshot(fixture(valueType)), true);
    assert.equal(state.connections.every((edge) => isValidConnection(edge, state.nodes)), true);
    const saved = workflowSnapshot();
    assert.deepEqual(saved.nodes.find((node) => node.id === 'get').arguments, { value_type: valueType, index_source: 'port' });
    assert.equal(loadSnapshot(saved), true);
    assert.deepEqual(workflowSnapshot(), saved);
    valid.push(saved);
  }
  for (const valueType of ['list-content', 'list-message', 'list-struct:task']) {
    for (const index of [0, 1, -1, -2]) {
      const workflow = fixture(valueType);
      workflow.nodes.find((node) => node.id === 'get').arguments = { value_type: valueType, index_source: 'fixed', index };
      workflow.connections = workflow.connections.filter((edge) => edge.toPortId !== 'index-in');
      assert.equal(loadSnapshot(workflow), true);
      const node = state.nodes.find((node) => node.id === 'get');
      assert.equal(portsForNode(node).some((port) => port.id === 'index-in'), false);
      const saved = workflowSnapshot();
      assert.deepEqual(saved.nodes.find((node) => node.id === 'get').arguments, { value_type: valueType, index_source: 'fixed', index });
      assert.equal(loadSnapshot(saved), true);
      assert.deepEqual(workflowSnapshot(), saved);
      valid.push(saved);
    }
  }
  const invalid = [];
  for (const valueType of ['content', 'number', 'list-number', 'list-struct:missing', null, '']) {
    const workflow = fixture();
    workflow.nodes[1].arguments.value_type = valueType;
    assert.equal(loadSnapshot(workflow), false, String(valueType));
    invalid.push(workflow);
  }
  for (const args of [undefined, {}, { value_type: 'list-content', index_source: 'fixed' }]) {
    const workflow = fixture();
    workflow.nodes[1].arguments = args;
    assert.equal(loadSnapshot(workflow), false);
    invalid.push(workflow);
  }
  for (const source of ['', null, true, 'invalid']) {
    const workflow = fixture();
    workflow.nodes.find((node) => node.id === 'get').arguments.index_source = source;
    assert.equal(loadSnapshot(workflow), false);
    invalid.push(workflow);
  }
  for (const index of [null, true, false, '', '0', 0.5, -0.5, [], {}]) {
    const workflow = fixture();
    Object.assign(workflow.nodes.find((node) => node.id === 'get').arguments, { index_source: 'fixed', index });
    assert.equal(loadSnapshot(workflow), false);
    invalid.push(workflow);
  }
  const staleIndexPort = fixture();
  Object.assign(staleIndexPort.nodes.find((node) => node.id === 'get').arguments, { index_source: 'fixed', index: 0 });
  invalid.push(staleIndexPort);
  for (const [port, type] of [['list-in', 'list-message'], ['index-in', 'content'], ['workflow:result', 'number']]) {
    const workflow = fixture();
    const edge = workflow.connections.find((edge) => edge.toPortId === port);
    edge.type = type;
    assert.equal(isValidConnection(edge, workflow.nodes.map((node) => node.type === 'list_get' ? { ...node, ...node.arguments } : node)), false);
    invalid.push(workflow);
  }
  const script = `import json, sys
sys.path.insert(0, sys.argv[1])
from workflow_validator import WorkflowValidationError, validate_workflow
cases = json.load(sys.stdin)
for workflow in cases["valid"]:
    validate_workflow(workflow)
    if sys.argv[1] != "agent_runtime": continue
    from workflow_parser import parse_workflow
    from workflow_nodes import propagate_workflow_output
    from test_support import run_scheduled_workflow
    arguments = next(node for node in workflow["nodes"] if node["type"] == "list_get")["arguments"]
    value_type = arguments["value_type"]
    values = ["first", "last"] if value_type == "list-content" else [{"role":"user","content":"first"}, {"role":"assistant","content":"last"}] if value_type == "list-message" else [{"name":"first"}, {"name":"last"}]
    for index in (0, 1, 1.0, -1, -2, -1.0):
        graph = parse_workflow(workflow)
        payload = json.dumps(values) if value_type.startswith("list-struct:") else values
        propagate_workflow_output(graph, graph[0], "workflow:items", payload)
        propagate_workflow_output(graph, graph[0], "workflow:index", index)
        result = run_scheduled_workflow(graph, 0)["result"]
        if value_type.startswith("list-struct:"): result = json.loads(result)
        expected_index = arguments["index"] if arguments.get("index_source") == "fixed" else index
        assert result == values[int(expected_index)]
for workflow in cases["invalid"]:
    try: validate_workflow(workflow)
    except WorkflowValidationError: pass
    else: raise AssertionError("invalid list_get accepted")`;
  for (const backend of ['agent_runtime', 'manager_webui']) {
    const result = spawnSync(process.env.PYTHON || 'python', ['-c', script, backend], {
      cwd: fileURLToPath(new URL('..', import.meta.url)), input: JSON.stringify({ valid, invalid }), encoding: 'utf8', timeout: 30000,
    });
    assert.ifError(result.error);
    assert.equal(result.status, 0, `${backend}: ${result.stderr}`);
  }
});

test('changing list type removes incompatible list and item edges but retains the numeric index', () => {
  assert.equal(loadSnapshot(fixture()), true);
  const node = state.nodes.find((item) => item.id === 'get');
  const field = { value: '', handlers: {}, options: [], addEventListener(event, callback) { this.handlers[event] = callback; },
    add(option) { this.options.push(option); option.remove = () => { this.options = this.options.filter((item) => item !== option); }; } };
  const previousOption = globalThis.Option;
  globalThis.Option = class { constructor(text, value) { this.text = text; this.value = value; } };
  try {
    for (const type of ['list-content', 'list-message']) field.add(new Option(type, type));
    let changes = 0;
    const indexFields = { '[data-field="index_source"]': { value: '', addEventListener() {} }, '[data-field="index"]': { value: '', addEventListener() {} }, '[data-index-field]': { hidden: true } };
    const context = { elements: { inspectorContent: { querySelector: (selector) => selector === '[data-field="value_type"]' ? field : indexFields[selector] } }, markChanged() { changes += 1; }, editor: { renderNodes() {} }, renderInspector() {} };
    bindStructureInspector(node, context);
    assert.deepEqual(field.options.map((option) => option.value), ['list-content', 'list-message', 'list-struct:task']);
    assert.equal(field.value, 'list-content');
    field.value = 'list-message';
    field.handlers.change();
    assert.equal(node.value_type, 'list-message');
    assert.equal(state.connections.some((edge) => edge.toPortId === 'list-in'), false);
    assert.equal(state.connections.some((edge) => edge.fromPortId === 'item-out'), false);
    assert.equal(state.connections.some((edge) => edge.toPortId === 'index-in'), true);
    assert.equal(state.connections.filter((edge) => edge.type === 'control').length, 2);
    assert.equal(changes, 1);
  } finally { globalThis.Option = previousOption; }
});

test('renaming a Struct preserves lookup input and element output type references', () => {
  const workflow = fixture('list-struct:task');
  workflow.metadata.structs = [{ ...task, id: 'renamed', name: 'Renamed' }];
  remapStructReferences(workflow, new Map([['task', 'renamed']]));
  assert.equal(loadSnapshot(workflow), true);
  const node = state.nodes.find((node) => node.id === 'get');
  assert.equal(node.value_type, 'list-struct:renamed');
  assert.equal(portsForNode(node).find((port) => port.id === 'item-out').type, 'struct:renamed');
  assert.equal(state.connections.length, workflow.connections.length);
  assert.equal(loadSnapshot(workflowSnapshot()), true);
});

test('the library and inspector expose typed lookup without silently fixing the index', () => {
  const html = readFileSync(new URL('./static/workflow_edit.html', import.meta.url), 'utf8');
  assert.match(html, /data-add-node="list_get"/);
  const template = html.match(/<template id="list_getInspectorTemplate">([\s\S]*?)<\/template>/)[1];
  assert.match(template, /data-field="value_type"/);
  assert.match(template, /value="list-content"/);
  assert.match(template, /value="list-message"/);
  assert.match(template, /data-field="index_source"/);
  assert.match(template, /value="fixed"/);
  assert.match(template, /value="port"/);
  assert.match(template, /data-field="index"[^>]*type="number"[^>]*step="1"/);
  assert.doesNotMatch(template, /data-field="index"[^>]*min=/);
  assert.doesNotMatch(template, /<p\b[^>]*class="field-hint"/);
});


test('index source switching updates ports, removes only the old index edge, and keeps fixed values numeric', () => {
  assert.equal(loadSnapshot(fixture()), true);
  const node = state.nodes.find((item) => item.id === 'get');
  const makeField = (value = '') => ({
    value, handlers: {}, options: [], validationMessage: '',
    addEventListener(event, callback) { this.handlers[event] = callback; },
    setCustomValidity(message) { this.validationMessage = message; },
    checkValidity() { return this.validationMessage === ''; },
    reportValidity() { this.reported = true; },
    add(option) { this.options.push(option); option.remove = () => { this.options = this.options.filter((item) => item !== option); }; },
  });
  const fields = {
    '[data-field="value_type"]': makeField(),
    '[data-field="index_source"]': makeField(),
    '[data-field="index"]': makeField(),
    '[data-index-field]': { hidden: true },
  };
  const previousOption = globalThis.Option;
  globalThis.Option = class { constructor(text, value) { this.text = text; this.value = value; } };
  try {
    const source = fields['[data-field="index_source"]'];
    const index = fields['[data-field="index"]'];
    const container = fields['[data-index-field]'];
    const edges = state.connections.filter((edge) => edge.toPortId !== 'index-in');
    let changes = 0;
    const context = { elements: { inspectorContent: { querySelector: (selector) => fields[selector] } },
      markChanged() { changes += 1; }, editor: { renderNodes() {} }, renderInspector() {} };
    bindStructureInspector(node, context);
    assert.equal(source.value, 'port');
    assert.equal(container.hidden, true);
    source.value = 'fixed';
    source.handlers.change();
    assert.equal(node.index_source, 'fixed');
    assert.equal(node.index, 0);
    assert.equal(container.hidden, false);
    assert.equal(portsForNode(node).some((port) => port.id === 'index-in'), false);
    assert.deepEqual(state.connections, edges);
    assert.equal(changes, 1);
    index.value = '1';
    index.handlers.input();
    assert.equal(node.index, 1);
    assert.equal(typeof node.index, 'number');
    assert.equal(workflowSnapshot().nodes.find((node) => node.id === 'get').arguments.index, 1);
    index.value = '-1';
    index.handlers.input();
    assert.equal(node.index, -1);
    assert.equal(index.validationMessage, '');
    assert.equal(workflowSnapshot().nodes.find((node) => node.id === 'get').arguments.index, -1);
    for (const invalid of ['', '0.5', '-0.5', 'NaN', 'Infinity']) {
      index.value = invalid;
      index.handlers.input();
      assert.notEqual(index.validationMessage, '');
      assert.equal(node.index, -1);
      index.handlers.change();
      assert.equal(Number(index.value), -1);
    }
    index.value = '0';
    index.handlers.input();
    assert.equal(node.index, 0);
    assert.equal(index.validationMessage, '');
    source.value = 'port';
    source.handlers.change();
    assert.equal(node.index_source, 'port');
    assert.equal(container.hidden, true);
    assert.equal(portsForNode(node).find((port) => port.id === 'index-in').type, 'number');
    assert.deepEqual(state.connections, edges);
    const edge = fixture().connections.find((edge) => edge.toPortId === 'index-in');
    assert.equal(isValidConnection(edge, state.nodes), true);
    bindStructureInspector(node, context);
    assert.equal(Number(index.value), 0);
  } finally { globalThis.Option = previousOption; }
});
