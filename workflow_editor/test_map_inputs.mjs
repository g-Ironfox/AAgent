import assert from 'node:assert/strict';
import { test } from 'node:test';
import { createNode, portsForNode } from './static/workflow/domain/node-contract.js';
import { isValidConnection } from './static/workflow/domain/connection-rules.js';
import { loadSnapshot, state, workflowSnapshot } from './static/workflow/domain/serialization.js';
import { bindStructureInspector } from './static/workflow/inspector/structure.js';

function fixture() {
  return {
    schema_version: '1.6', name: 'map_ports',
    input_ports: [{ name: 'text', type: 'content' }],
    output_ports: [{ name: 'result', type: 'map-content' }],
    nodes: [
      { id: 'input', type: 'input' },
      { id: 'map', type: 'construct_map_content', dataInputPorts: ['value-7'], arguments: { mappings: [
        { key: 'fixed', value: '' },
        { key: 'dynamic', value_source: 'port', port_id: 'value-7' },
      ] } },
      { id: 'output', type: 'output' },
    ],
    connections: [
      { id: 'data-in', fromId: 'input', fromPortId: 'workflow:text', toId: 'map', toPortId: 'value-7', type: 'content' },
      { id: 'data-out', fromId: 'map', fromPortId: 'map-out', toId: 'output', toPortId: 'workflow:result', type: 'map-content' },
    ],
  };
}

function inspectorHarness() {
  const container = { rows: [], append(row) { this.rows.push(row); } };
  const addButton = element();
  const context = {
    elements: { inspectorContent: { querySelector: (selector) => selector === '[data-content-mappings]' ? container : addButton } },
    markChanged() {}, editor: { renderNodes() {} }, renderInspector() {}, renderInterfaceContract() {},
  };
  function element() {
    return { value: '', hidden: false, handlers: {}, addEventListener(event, callback) { this.handlers[event] = callback; } };
  }
  globalThis.document = { createElement() {
    const fields = new Map();
    return { querySelector(selector) {
      if (!fields.has(selector)) fields.set(selector, element());
      return fields.get(selector);
    } };
  } };
  return { addButton, bind(node) {
    container.rows = [];
    bindStructureInspector(node, context);
    return container.rows;
  } };
}

test('dynamic and fixed values survive save and reload', () => {
  assert.equal(loadSnapshot(fixture()), true);
  const saved = workflowSnapshot();
  assert.equal(loadSnapshot(saved), true);
  assert.deepEqual(workflowSnapshot(), saved);
  assert.equal(state.connections.length, 2);
  assert.equal(portsForNode(state.nodes[1]).find((port) => port.id === 'value-7').type, 'content');
});

test('legacy mappings and default Map nodes remain fixed-value compatible', () => {
  const document = fixture();
  document.nodes[1].arguments.mappings = [{ key: 'old', value: '' }];
  delete document.nodes[1].dataInputPorts;
  document.connections = [];
  assert.equal(loadSnapshot(document), true);
  assert.deepEqual(state.nodes[1].dataInputPorts, []);
  assert.deepEqual(createNode('construct_map_content', []).mappings, [{ key: 'key1', value: '' }]);
});

test('malformed map ports are rejected and only content connections are accepted', () => {
  for (const mutate of [
    (node) => { node.arguments.mappings[1].value = 'ambiguous'; },
    (node) => { node.arguments.mappings[1].port_id = 'control-in'; node.dataInputPorts = ['control-in']; },
    (node) => { node.dataInputPorts = ['wrong']; },
    (node) => { delete node.dataInputPorts; },
  ]) {
    const document = fixture();
    mutate(document.nodes[1]);
    assert.equal(loadSnapshot(document), false);
  }
  assert.equal(loadSnapshot(fixture()), true);
  const connection = fixture().connections[0];
  assert.equal(isValidConnection(connection, state.nodes), true);
  assert.equal(isValidConnection({ ...connection, type: 'message' }, state.nodes), false);
});

test('switching value source creates and removes only its input port', () => {
  assert.equal(loadSnapshot(fixture()), true);
  const harness = inspectorHarness();
  try {
    const node = state.nodes[1];
    let rows = harness.bind(node);
    const source = rows[0].querySelector('select');
    source.value = 'port';
    source.handlers.change();
    assert.deepEqual(node.dataInputPorts, ['map-value-in-0', 'value-7']);
    state.connections.push({ id: 'new-data', fromId: 'input', fromPortId: 'workflow:text', toId: 'map', toPortId: 'map-value-in-0', type: 'content' });
    rows = harness.bind(node);
    const fixedSource = rows[0].querySelector('select');
    fixedSource.value = 'fixed';
    fixedSource.handlers.change();
    assert.deepEqual(node.dataInputPorts, ['value-7']);
    assert.equal(state.connections.some((item) => item.id === 'new-data'), false);
    assert.equal(state.connections.some((item) => item.toPortId === 'value-7'), true);
  } finally {
    delete globalThis.document;
  }
});
