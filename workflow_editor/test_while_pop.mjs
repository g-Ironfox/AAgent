import assert from 'node:assert/strict';
import { test } from 'node:test';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { createNode, portsForNode, setNodeStructs } from './static/workflow/domain/node-contract.js';
import { loadSnapshot, state, workflowSnapshot } from './static/workflow/domain/serialization.js';
import { isValidConnection } from './static/workflow/domain/connection-rules.js';
import { compileLifecycles } from './static/workflow/domain/lifecycle.js';
import { bindStructureInspector } from './static/workflow/inspector/structure.js';

const control = (fromId, toId, fromPortId = 'control-out', toPortId = 'control-in') => ({ id: `${fromId}-${fromPortId}`, fromId, fromPortId, toId, toPortId, type: 'control' });
const data = (fromId, toId, fromPortId, toPortId, type = 'content') => ({ id: `${fromId}-${toId}-${fromPortId}`, fromId, fromPortId, toId, toPortId, type });
const task = { id: 'task', name: 'Task', color: '#123456', list_color: '#654321', fields: [{ name: 'name', type: 'content', required: true }] };
function fixture(valueType = 'list-content', fixed = false) {
  const itemType = valueType.slice(5);
  return {
    schema_version: '2.0', name: 'while_pop', input_ports: [{ name: 'context_id', type: 'content' }], output_ports: [],
    metadata: { structs: [task], tools: [] },
    nodes: [
      { id: 'input', type: 'input', workflowPorts: [{ id: 'workflow:context_id', name: 'context_id', type: 'content' }] },
      { id: 'pop', type: 'while_pop', arguments: { value_type: valueType, ...(fixed ? { context_id_source: 'fixed', context_id: 'queue', position: 'start' } : {}) } },
      { id: 'body', type: 'context_write', arguments: { value_type: itemType, context_id_source: 'fixed', context_id: 'result' } },
      { id: 'output', type: 'output', workflowPorts: [] },
    ],
    connections: [control('input', 'pop'), control('pop', 'body', 'loop-out'), control('body', 'pop', 'control-out', 'loop-in'), control('pop', 'output'),
      data('pop', 'body', 'item-out', 'value-in', itemType), ...(fixed ? [] : [data('input', 'pop', 'workflow:context_id', 'context-id')])],
  };
}

test('while_pop defaults to a context ID input and tail pop with foreach controls', () => {
  const node = createNode('while_pop', []);
  assert.equal(node.value_type, 'list-content');
  assert.equal(node.position, 'end');
  assert.equal(node.context_id_source, 'port');
  const ports = portsForNode(node);
  assert.deepEqual(ports.map((port) => port.id), ['control-in', 'loop-in', 'context-id', 'control-out', 'loop-out', 'item-out']);
  assert.equal(ports.find((port) => port.id === 'context-id').type, 'content');
  assert.equal(ports.find((port) => port.id === 'item-out').type, 'content');
});

test('typed list configuration determines the item output and Struct color', () => {
  for (const [value_type, output] of [['list-content', 'content'], ['list-message', 'message'], ['list-struct:task', 'struct:task']]) {
    const node = { id: 'pop', type: 'while_pop', value_type };
    setNodeStructs([node], [task]);
    const item = portsForNode(node).find((port) => port.id === 'item-out');
    assert.equal(item.type, output);
    if (output === 'struct:task') assert.equal(item.color, task.color);
    assert.equal(portsForNode({ ...node, context_id_source: 'fixed' }).some((port) => port.id === 'context-id'), false);
  }
});

test('while_pop round-trips all list types and ID modes through both backends', () => {
  const workflows = [];
  for (const kind of ['list-content', 'list-message', 'list-struct:task']) {
    for (const fixed of [false, true]) {
      assert.equal(loadSnapshot(fixture(kind, fixed)), true);
      const saved = workflowSnapshot();
      const args = saved.nodes.find((node) => node.id === 'pop').arguments;
      assert.equal(args.position, fixed ? 'start' : 'end');
      assert.equal(args.context_id_source, fixed ? 'fixed' : 'port');
      assert.equal(state.connections.length, fixture(kind, fixed).connections.length);
      assert.equal(loadSnapshot(saved), true);
      assert.deepEqual(workflowSnapshot(), saved);
      workflows.push(saved);
    }
  }
  const script = `import json, sys\nsys.path.insert(0, sys.argv[1])\nfrom workflow_validator import validate_workflow\nfor workflow in json.load(sys.stdin): validate_workflow(workflow)`;
  for (const backend of ['agent_runtime', 'manager_webui']) {
    const result = spawnSync(process.env.PYTHON || 'python', ['-c', script, backend], {
      cwd: fileURLToPath(new URL('..', import.meta.url)), input: JSON.stringify(workflows), encoding: 'utf8', timeout: 30000,
    });
    assert.ifError(result.error);
    assert.equal(result.status, 0, `${backend}: ${result.stderr}`);
  }
});

test('while_pop only accepts context IDs and keeps popped items within the loop', () => {
  assert.equal(loadSnapshot(fixture()), true);
  const idEdge = state.connections.find((edge) => edge.toPortId === 'context-id');
  assert.equal(isValidConnection(idEdge, state.nodes), true);
  assert.equal(isValidConnection({ ...idEdge, type: 'list-content' }, state.nodes), false);
  const compiled = compileLifecycles(state);
  assert.deepEqual(compiled.errors, []);
  assert.equal(compiled.outputScopes.get('pop')['item-out'], compiled.nodeScopes.get('body'));
  assert.notEqual(compiled.nodeScopes.get('pop'), compiled.nodeScopes.get('body'));
  assert.equal(compiled.nodeScopes.get('pop'), compiled.nodeScopes.get('output'));
  const graph = fixture();
  graph.connections.push(data('pop', 'output', 'item-out', 'value'));
  assert.ok(compileLifecycles(graph).errors.some((error) => /生命周期|作用域|空间/.test(error.message)));
});

test('while_pop rejects scalar or unknown Struct contexts when loading', () => {
  for (const valueType of ['content', 'map-content', 'struct:task', 'list-struct:missing']) {
    assert.equal(loadSnapshot(fixture(valueType)), false, valueType);
  }
  const missing = fixture('list-content', true);
  delete missing.nodes[1].arguments.context_id;
  assert.equal(loadSnapshot(missing), false);
});

test('while_pop inspector offers only lists and reconciles type and ID source changes', () => {
  assert.equal(loadSnapshot(fixture()), true);
  const node = state.nodes.find((item) => item.id === 'pop');
  const field = () => ({ value: '', hidden: false, handlers: {}, addEventListener(event, callback) { this.handlers[event] = callback; } });
  const typeField = { ...field(), options: [], add(option) {
    this.options.push(option);
    option.remove = () => { this.options = this.options.filter((item) => item !== option); };
  } };
  globalThis.Option = class { constructor(text, value) { this.text = text; this.value = value; } };
  for (const type of ['list-content', 'list-message']) typeField.add(new Option(type, type));
  const source = field(); const id = field(); const idContainer = field();
  const fields = { '[data-field="value_type"]': typeField, '[data-field="context_id_source"]': source, '[data-field="context_id"]': id, '[data-context-id-field]': idContainer };
  let changes = 0;
  const context = { elements: { inspectorContent: { querySelector: (selector) => fields[selector] } }, markChanged() { changes += 1; }, editor: { renderNodes() {} }, renderInspector() {} };
  bindStructureInspector(node, context);
  assert.deepEqual(typeField.options.map((option) => option.value), ['list-content', 'list-message', 'list-struct:task']);
  assert.equal(idContainer.hidden, true);
  typeField.value = 'list-struct:task';
  typeField.handlers.change();
  assert.equal(node.value_type, 'list-struct:task');
  assert.equal(state.connections.some((edge) => edge.fromPortId === 'item-out'), false);
  source.value = 'fixed'; source.handlers.change();
  assert.equal(node.context_id_source, 'fixed');
  assert.equal(idContainer.hidden, false);
  assert.equal(state.connections.some((edge) => edge.toPortId === 'context-id'), false);
  id.value = ' queue '; id.handlers.change();
  assert.equal(node.context_id, ' queue ');
  assert.equal(changes, 3);
});
