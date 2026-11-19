import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { createNode, portsForNode } from './static/workflow/domain/node-contract.js';
import { isValidConnection } from './static/workflow/domain/connection-rules.js';
import { bindStructureInspector } from './static/workflow/inspector/structure.js';
import { workflowCanvasSvg } from '../webui_py/static/workflow_canvas.mjs';
import { loadSnapshot, state, workflowSnapshot } from './static/workflow/domain/serialization.js';

function fixture(valueType = 'list-content') {
  const workflow = {
    schema_version: '2.0', name: 'list_slice', metadata: { structs: [], tools: [] },
    input_ports: [{ name: 'items', type: valueType }], output_ports: [{ name: 'items', type: valueType }],
    subprocess_workflow_files: [], remote_tools: [],
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

test('typed list_slice snapshots survive save and reload and validate in the agent', () => {
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
  for (let mask = 0; mask < 8; mask += 1) {
    const workflow = fixture();
    const args = workflow.nodes[1].arguments;
    for (const [index, name] of ['start', 'stop', 'step'].entries()) {
      args[`${name}_source`] = mask & (1 << index) ? 'fixed' : 'port';
      if (args[`${name}_source`] === 'fixed') args[name] = { start: -4, stop: null, step: 2 }[name];
    }
    assert.equal(loadSnapshot(workflow), true);
    const saved = workflowSnapshot();
    assert.deepEqual(saved.nodes.find((node) => node.id === 'slice').arguments, args);
    assert.equal(loadSnapshot(saved), true);
    assert.deepEqual(workflowSnapshot(), saved);
    valid.push(saved);
  }
  const invalid = [];
  for (const name of ['start', 'stop', 'step']) {
    for (const patch of [{ [`${name}_source`]: 'bad' }, ...[true, 1.5, '2', [], {}].map((value) => ({ [`${name}_source`]: 'fixed', [name]: value }))]) {
      const workflow = fixture();
      Object.assign(workflow.nodes[1].arguments, patch);
      assert.equal(loadSnapshot(workflow), false);
      invalid.push(workflow);
    }
  }
  const zeroStep = fixture();
  Object.assign(zeroStep.nodes[1].arguments, { step_source: 'fixed', step: 0 });
  assert.equal(loadSnapshot(zeroStep), false);
  invalid.push(zeroStep);
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
  const result = spawnSync(process.env.PYTHON || 'python', ['-c', script, 'agent'], {
    cwd: fileURLToPath(new URL('..', import.meta.url)), input: JSON.stringify({ valid, invalid }), encoding: 'utf8', timeout: 30000,
  });
  assert.ifError(result.error);
  assert.equal(result.status, 0, result.stderr);
});

test('list_slice is available in the node library and canvas contracts', () => {
  const html = readFileSync(new URL('./static/workflow_edit.html', import.meta.url), 'utf8');
  assert.match(html, /data-add-node="list_slice"/);
  assert.match(html, /id="list_sliceInspectorTemplate"/);
  assert.match(html, /value="list-message"/);
});


test('switching each slice source removes only its own edge and validates fixed input', () => {
  const workflow = fixture();
  for (const name of ['start', 'stop', 'step']) {
    workflow.input_ports.push({ name, type: 'number' });
    workflow.nodes[0].workflowPorts.push({ id: `workflow:${name}`, name, type: 'number' });
    workflow.connections.push({ id: name, fromId: 'input', fromPortId: `workflow:${name}`, toId: 'slice', toPortId: `${name}-in`, type: 'number' });
  }
  assert.equal(loadSnapshot(workflow), true);
  const node = state.nodes.find((item) => item.id === 'slice');
  const makeField = () => ({
    value: '', handlers: {}, options: [], validity: { badInput: false }, validationMessage: '',
    addEventListener(event, callback) { this.handlers[event] = callback; },
    setCustomValidity(message) { this.validationMessage = message; },
    checkValidity() { return !this.validationMessage; }, reportValidity() {},
  });
  const fields = { '[data-field="value_type"]': makeField() };
  for (const name of ['start', 'stop', 'step']) {
    fields[`[data-field="${name}_source"]`] = makeField();
    fields[`[data-field="${name}"]`] = makeField();
    fields[`[data-${name}-field]`] = { hidden: true };
  }
  const context = { elements: { inspectorContent: { querySelector: (selector) => fields[selector] } },
    markChanged() {}, editor: { renderNodes() {} }, renderInspector() {} };
  bindStructureInspector(node, context);
  for (const name of ['start', 'stop', 'step']) {
    const source = fields[`[data-field="${name}_source"]`];
    const value = fields[`[data-field="${name}"]`];
    assert.equal(source.value, 'port');
    const previousEdges = state.connections.filter((edge) => edge.toPortId !== `${name}-in`);
    source.value = 'fixed'; source.handlers.change();
    assert.equal(fields[`[data-${name}-field]`].hidden, false);
    assert.equal(portsForNode(node).some((port) => port.id === `${name}-in`), false);
    assert.deepEqual(state.connections, previousEdges);
    assert.equal(isValidConnection(workflow.connections.find((edge) => edge.id === name), state.nodes), false);
    value.value = '-2'; value.handlers.input();
    assert.equal(node[name], -2);
    for (const invalid of name === 'step' ? ['0', '1.5'] : ['1.5']) {
      value.value = invalid; value.handlers.input();
      assert.ok(value.validationMessage);
      assert.equal(node[name], -2);
      value.handlers.change();
      assert.equal(value.value, -2);
    }
    value.value = ''; value.validity.badInput = true; value.handlers.input();
    assert.ok(value.validationMessage);
    assert.equal(node[name], -2);
    value.validity.badInput = false; value.handlers.input();
    assert.equal(node[name], null);
    assert.equal(value.validationMessage, '');
    value.value = '-1'; value.handlers.input();
    source.value = 'port'; source.handlers.change();
    assert.equal(fields[`[data-${name}-field]`].hidden, true);
    assert.ok(portsForNode(node).some((port) => port.id === `${name}-in`));
    source.value = 'fixed'; source.handlers.change();
    assert.equal(node[name], -1);
  }
  const saved = workflowSnapshot();
  assert.equal(loadSnapshot(saved), true);
  for (const name of ['start', 'stop', 'step']) {
    assert.equal(state.nodes.find((item) => item.id === 'slice')[name], -1);
  }
});

test('slice inspector offers independent inputs and canvas renders connected port bounds', () => {
  const html = readFileSync(new URL('./static/workflow_edit.html', import.meta.url), 'utf8');
  const template = html.match(/<template id="list_sliceInspectorTemplate">([\s\S]*?)<\/template>/)[1];
  for (const name of ['start', 'stop', 'step']) {
    assert.ok(template.includes(`data-field="${name}_source"`));
    assert.ok(template.includes(`data-field="${name}" type="number" step="1"`));
  }
  const workflow = fixture();
  Object.assign(workflow.nodes[1].arguments, { start_source: 'fixed', start: 1, step_source: 'fixed', step: 2 });
  workflow.connections.push({ id: 'stop', fromId: 'input', fromPortId: 'workflow:stop', toId: 'slice', toPortId: 'stop-in', type: 'number' });
  const svg = workflowCanvasSvg(workflow);
  assert.doesNotMatch(svg, />start-in</);
  assert.doesNotMatch(svg, />step-in</);
  assert.match(svg, />stop-in</);
});
