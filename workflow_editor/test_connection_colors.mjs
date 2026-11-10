import assert from 'node:assert/strict';
import { test } from 'node:test';
import { createWorkflowEditor } from './static/workflow/editor.js';
import { state } from './static/workflow/domain/serialization.js';

test('editor renders Struct and list connections with independent colors and legacy fallback', () => {
  const previousDocument = globalThis.document;
  const previousMetadata = state.metadata;
  const previousConnections = state.connections;
  const rules = [];
  const sheet = {
    cssRules: rules,
    insertRule(selector, index) {
      const declarations = new Map();
      rules.splice(index, 0, { selector, declarations, style: {
        set cssText(value) { if (value === '') declarations.clear(); },
        setProperty(name, value) { declarations.set(name, value); },
      } });
      return index;
    },
  };
  const rect = () => ({ left: 0, top: 0, width: 12, height: 12 });
  const connection = { id: 'colored-edge', fromId: 'source', fromPortId: 'out', toId: 'target', toPortId: 'in', type: 'struct:Profile' };
  const nodes = [['source', 'out', 'output'], ['target', 'in', 'input']].map(([nodeId, portId, direction]) => ({
    dataset: { nodeId },
    querySelectorAll: () => [{ dataset: { portId, portDirection: direction, portType: connection.type }, getBoundingClientRect: rect }],
  }));
  let paths = [];
  globalThis.document = {
    styleSheets: [sheet], querySelectorAll: () => [{ href: '/css/workflow.css', sheet }], addEventListener() {},
    createElementNS() {
      const element = { setAttribute() {}, classes: [] };
      element.classList = { add: (name) => element.classes.push(name) };
      return element;
    },
  };
  const elements = {
    canvas: { addEventListener() {}, getBoundingClientRect: rect, scrollLeft: 0, scrollTop: 0, clientWidth: 500, clientHeight: 400 },
    nodeLayer: { querySelectorAll: () => nodes, scrollWidth: 500, scrollHeight: 400 },
    connectionLayer: { setAttribute() {}, replaceChildren(...children) { paths = children; } },
    connectionCount: {},
  };
  try {
    state.metadata = { structs: [{ id: 'Profile', color: '#3A7D68', list_color: '#3976A8' }] };
    state.connections = [connection];
    const editor = createWorkflowEditor(elements, () => {});
    const assertColor = (expected) => {
      editor.editorState.connectionDrag = {
        type: connection.type, anchorNodeId: 'source', anchorPortId: 'out', anchorDirection: 'output', pointer: { x: 100, y: 100 },
      };
      editor.renderConnections();
      assert.equal(paths.length, 2);
      for (const path of paths) {
        assert.equal(path.classes.length, 1);
        const className = path.classes[0];
        const rule = rules.find((item) => item.selector.startsWith(`.${className}.${className} `));
        assert.equal(rule.declarations.get('--connection-color'), expected);
      }
    };
    assertColor('#3A7D68');
    connection.type = 'list-struct:Profile';
    assertColor('#3976A8');
    state.metadata.structs[0].list_color = '#D97706';
    assertColor('#D97706');
    delete state.metadata.structs[0].list_color;
    assertColor('#3A7D68');
  } finally {
    if (previousDocument === undefined) delete globalThis.document;
    else globalThis.document = previousDocument;
    state.metadata = previousMetadata;
    state.connections = previousConnections;
  }
});
