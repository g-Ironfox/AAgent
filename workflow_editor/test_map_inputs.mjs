import assert from 'node:assert/strict';
import { test } from 'node:test';
import { createNode, portsForNode } from './static/workflow/domain/node-contract.js';
import { isValidConnection } from './static/workflow/domain/connection-rules.js';
import { addNode, loadSnapshot, state, workflowSnapshot } from './static/workflow/domain/serialization.js';
import { bindStructureInspector } from './static/workflow/inspector/structure.js';
import { setRuntimeStyles } from './static/workflow/domain/runtime-styles.js';

function fixture() {
  return {
    schema_version: '2.0', name: 'map_ports',
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
  const routeOptions = { rows: [], append(row) { this.rows.push(row); } };
  const addButton = element();
  let changes = 0;
  const context = {
    elements: { inspectorContent: { querySelector: (selector) => ({
      '[data-content-mappings]': container,
      '[data-route-options]': routeOptions,
      '[data-add-branch]': addButton,
    })[selector] || addButton } },
    markChanged() { changes += 1; }, editor: { renderNodes() {} }, renderInspector() {}, renderInterfaceContract() {},
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
  return { addButton, get changes() { return changes; }, bind(node) {
    container.rows = [];
    routeOptions.rows = [];
    bindStructureInspector(node, context);
    return node.type === 'router' ? routeOptions.rows : container.rows;
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

test('branch name input rejects duplicates without recording a change', () => {
  const workflow = {
    schema_version: '2.0', name: 'duplicate_branches',
    nodes: [
      { id: 'input', type: 'input' },
      { id: 'router', type: 'router', arguments: { branches: [
        { id: 'branch-one', name: 'First' },
        { id: 'branch-two', name: 'Second' },
      ] } },
      { id: 'output', type: 'output' },
    ],
    connections: [],
  };
  assert.equal(loadSnapshot(workflow), true);
  const harness = inspectorHarness();
  try {
    const rows = harness.bind(state.nodes[1]);
    const input = rows[0].querySelector('[data-branch-name]');
    input.value = 'Second';
    input.handlers.input();
    assert.equal(input.value, 'First');
    assert.equal(state.nodes[1].branches[0].name, 'First');
    assert.equal(harness.changes, 0);
  } finally {
    delete globalThis.document;
  }
});

test('workflow validation rejects duplicate branch names', () => {
  const workflow = {
    schema_version: '2.0', name: 'duplicate_branches',
    nodes: [
      { id: 'input', type: 'input' },
      { id: 'router', type: 'router', arguments: { branches: [
        { id: 'branch-one', name: 'Same' },
        { id: 'branch-two', name: 'Same' },
      ] } },
      { id: 'output', type: 'output' },
    ],
    connections: [],
  };
  assert.equal(loadSnapshot(workflow), false);
});

test('workflow-local Struct declarations survive load and expose colored typed ports', () => {
  const workflow = {
    schema_version: '2.0', name: 'struct_ports',
    metadata: { structs: [{ id: 'profile', name: 'Profile', color: '#3A7D68', fields: [{ name: 'display_name', type: 'content', required: true }] }] },
    input_ports: [], output_ports: [],
    nodes: [
      { id: 'input', type: 'input' },
      { id: 'make', type: 'construct_struct', dataInputPorts: ['display_name'], arguments: { struct_id: 'profile' } },
      { id: 'output', type: 'output' },
    ], connections: [],
  };
  assert.equal(loadSnapshot(workflow), true);
  const saved = workflowSnapshot();
  assert.deepEqual(saved.metadata.structs, workflow.metadata.structs);
  const port = portsForNode(state.nodes[1]).find((item) => item.id === 'struct-out');
  assert.equal(port.type, 'struct:profile');
  assert.equal(port.color, '#3A7D68');
});

test('Struct lists have a distinct declared color on list node ports', () => {
  const structs = [{ id: 'profile', name: 'Profile', color: '#3A7D68', list_color: '#3976A8', fields: [] }];
  assert.equal(loadSnapshot({
    schema_version: '2.0', name: 'struct_list_colors', metadata: { structs },
    input_ports: [], output_ports: [],
    nodes: [
      { id: 'input', type: 'input' },
      { id: 'list', type: 'construct_list', arguments: { item_type: 'struct:profile', initial_value_count: 0 }, dataInputPorts: [] },
      { id: 'output', type: 'output' },
    ], connections: [],
  }), true);
  const output = portsForNode(state.nodes.find((node) => node.id === 'list')).find((port) => port.id === 'list-out');
  assert.equal(output.type, 'list-struct:profile');
  assert.equal(output.color, '#3976A8');

  const legacy = structuredClone(structs);
  delete legacy[0].list_color;
  assert.equal(loadSnapshot({ schema_version: '2.0', name: 'legacy_struct_list_colors', metadata: { structs: legacy }, input_ports: [], output_ports: [], nodes: [{ id: 'input', type: 'input' }, { id: 'list', type: 'construct_list', arguments: { item_type: 'struct:profile', initial_value_count: 0 }, dataInputPorts: [] }, { id: 'output', type: 'output' }], connections: [] }), true);
  assert.equal(portsForNode(state.nodes.find((node) => node.id === 'list')).find((port) => port.id === 'list-out').color, '#3A7D68');
});


test('Context value ports follow Struct and list colors with legacy fallback', () => {
  for (const listColor of ['#3976A8', undefined]) {
    const definition = { id: 'profile', name: 'Profile', color: '#3A7D68', fields: [] };
    if (listColor) definition.list_color = listColor;
    for (const valueType of ['struct:profile', 'list-struct:profile']) {
      assert.equal(loadSnapshot({
        schema_version: '2.0', name: 'context_colors', metadata: { structs: [definition] },
        input_ports: [], output_ports: [],
        nodes: [
          { id: 'input', type: 'input' },
          { id: 'create', type: 'context_create', arguments: { value_type: valueType } },
          { id: 'read', type: 'context_read', arguments: { value_type: valueType, context_id_source: 'port' } },
          { id: 'write', type: 'context_write', arguments: { value_type: valueType, context_id_source: 'port' } },
          { id: 'output', type: 'output' },
        ], connections: [],
      }), true);
      for (const [nodeId, portIds] of Object.entries({ create: ['initial-value'], read: ['value-out'], write: ['value-in', 'value-out'] })) {
        const ports = portsForNode(state.nodes.find((item) => item.id === nodeId));
        for (const portId of portIds) {
          const port = ports.find((item) => item.id === portId);
          assert.equal(port.type, valueType);
          assert.equal(port.color, valueType.startsWith('list-') ? (listColor || definition.color) : definition.color, `${nodeId}.${portId}`);
        }
        assert.ok(ports.filter((port) => port.type === 'content' || port.type === 'control').every((port) => !port.color));
      }
    }
  }
});

test('all five Struct node types can be created and round-trip before any type is selected', () => {
  assert.equal(loadSnapshot({
    schema_version: '2.0', name: 'unbound_struct_nodes',
    metadata: { structs: [] }, input_ports: [], output_ports: [],
    nodes: [{ id: 'input', type: 'input' }, { id: 'output', type: 'output' }], connections: [],
  }), true);
  const types = ['construct_struct', 'struct_get', 'struct_update', 'struct_to_json', 'json_to_struct'];
  for (const type of types) {
    const node = addNode(type);
    assert.ok(node, `${type} should be created without declarations`);
    assert.equal(portsForNode(node).filter((port) => port.type !== 'control').length, 0, type);
  }
  const saved = workflowSnapshot();
  assert.equal(loadSnapshot(saved), true);
  for (const node of state.nodes.filter((item) => types.includes(item.type))) {
    assert.equal(node.struct_id ?? node.value_type, '');
    assert.equal(portsForNode(node).filter((port) => port.type !== 'control').length, 0, node.type);
  }
});

test('Struct declarations do not implicitly bind newly created Struct nodes', () => {
  const structs = [{ id: 'profile', name: 'Profile', color: '#3A7D68', fields: [
    { name: 'name', type: 'content', required: true },
    { name: 'nickname', type: 'content', required: false },
  ] }];
  assert.equal(loadSnapshot({
    schema_version: '2.0', name: 'independent_struct_metadata', metadata: { structs },
    input_ports: [], output_ports: [],
    nodes: [{ id: 'input', type: 'input' }, { id: 'output', type: 'output' }], connections: [],
  }), true);
  for (const type of ['construct_struct', 'struct_get', 'struct_update', 'struct_to_json', 'json_to_struct']) {
    const node = addNode(type);
    assert.ok(node, `${type} should be created`);
    assert.equal(node.struct_id ?? node.value_type, '', type);
    assert.equal(portsForNode(node).filter((port) => port.type !== 'control').length, 0, type);
  }
  const saved = workflowSnapshot();
  assert.equal(loadSnapshot(saved), true);
  assert.deepEqual(workflowSnapshot().metadata.structs, structs);
});

test('Struct nodes bind a declared type from the Inspector and build their data ports', () => {
  const structs = [{ id: 'profile', name: 'Profile', color: '#3A7D68', fields: [
    { name: 'name', type: 'content', required: true },
    { name: 'nickname', type: 'content', required: false },
  ] }];
  assert.equal(loadSnapshot({
    schema_version: '2.0', name: 'inspector_struct_binding', metadata: { structs },
    input_ports: [], output_ports: [],
    nodes: [{ id: 'input', type: 'input' }, { id: 'output', type: 'output' }], connections: [],
  }), true);

  const types = ['construct_struct', 'struct_get', 'struct_update', 'struct_to_json', 'json_to_struct'];
  const nodes = types.map((type) => addNode(type));
  const previousDocument = globalThis.document;
  const previousOption = globalThis.Option;
  globalThis.Option = class {
    constructor(text, value) { this.text = text; this.value = value; this.disabled = false; }
  };
  const element = (options = []) => ({
    options: [...options], handlers: {}, children: [], value: '',
    add(option) { this.options.push(option); },
    addEventListener(event, callback) { this.handlers[event] = callback; },
    append(...children) { this.children.push(...children); },
    replaceChildren(...children) { this.children = children; },
    setAttribute() {},
  });
  globalThis.document = { createElement: () => element() };

  try {
    for (const node of nodes) {
      const structSelect = element();
      const fieldSelect = element();
      const missingSelect = element([new Option('报错', 'error'), new Option('Fallback', 'fallback')]);
      const valueTypeSelect = element();
      const structFields = element();
      const updateFields = element();
      const controls = new Map([
        ['[data-struct-id]', structSelect],
        ['[data-struct-field]', fieldSelect],
        ['[data-struct-missing]', missingSelect],
        ['[data-struct-value-type]', valueTypeSelect],
        ['[data-struct-fields]', structFields],
        ['[data-struct-update-fields]', updateFields],
      ]);
      const context = {
        elements: { inspectorContent: { querySelector: (selector) => controls.get(selector) || null } },
        markChanged() {}, editor: { renderNodes() {} }, renderInspector() {},
      };

      bindStructureInspector(node, context);
      const selector = ['struct_to_json', 'json_to_struct'].includes(node.type) ? valueTypeSelect : structSelect;
      selector.value = ['struct_to_json', 'json_to_struct'].includes(node.type) ? 'struct:profile' : 'profile';
      selector.handlers.change();

      const ports = portsForNode(node);
      assert.ok(ports.some((port) => port.type === 'struct:profile'), node.type);
      assert.ok(ports.some((port) => port.color === '#3A7D68'), node.type);
      if (node.type === 'construct_struct') assert.deepEqual(node.dataInputPorts, ['name', 'nickname']);
      if (node.type === 'struct_get') assert.ok(ports.some((port) => port.id === 'value-out'));
      if (node.type === 'struct_update') assert.ok(ports.some((port) => port.id === 'struct-in'));
    }
    const saved = workflowSnapshot();
    assert.equal(loadSnapshot(saved), true);
    for (const type of types) {
      const node = state.nodes.find((item) => item.type === type);
      assert.ok(portsForNode(node).some((port) => port.type !== 'control'), type);
    }
  } finally {
    if (previousDocument === undefined) delete globalThis.document;
    else globalThis.document = previousDocument;
    if (previousOption === undefined) delete globalThis.Option;
    else globalThis.Option = previousOption;
  }
});

test('runtime colors and layout use external stylesheet rules under strict CSP', () => {
  const rules = [];
  const sheet = {
    cssRules: rules,
    insertRule(selectorText, index) {
      const declarations = new Map();
      const style = {
        setProperty(name, value) {
          assert.match(name, /^(?:--[a-z0-9-]+|[a-z]+(?:-[a-z]+)*)$/, 'setProperty requires a CSS property name');
          declarations.set(name, value);
        },
        set cssText(value) { if (value === '') declarations.clear(); },
      };
      rules.splice(index, 0, { selectorText: selectorText.slice(0, selectorText.indexOf('{')).trim(), style, declarations });
      return index;
    },
  };
  const previousDocument = globalThis.document;
  const classes = new Set();
  const element = { classList: { add: (name) => classes.add(name) } };
  globalThis.document = {
    styleSheets: [sheet],
    querySelectorAll: () => [{ href: '/css/workflow.css?v=20', sheet }],
  };
  try {
    setRuntimeStyles(element, 'struct-color', { 'background-color': '#3A7D68' });
    setRuntimeStyles(element, 'struct-color', { 'background-color': '#D97706' });
    assert.equal(rules.length, 1);
    assert.match(rules[0].selectorText, /^\.(workflow-runtime-\d+)\.\1$/);
    assert.equal(rules[0].declarations.get('background-color'), '#D97706');
    assert.equal(classes.size, 1);
    assert.equal('style' in element, false);
  } finally {
    if (previousDocument === undefined) delete globalThis.document;
    else globalThis.document = previousDocument;
  }
});
