import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { createWorkflowEditor } from './static/workflow/editor.js';
import { createNode, portsForNode } from './static/workflow/domain/node-contract.js';
import { state } from './static/workflow/domain/serialization.js';

test('terminal input symbols have a visible background in the library and canvas', () => {
  const css = readFileSync(new URL('./static/css/workflow/layout.css', import.meta.url), 'utf8');
  const html = readFileSync(new URL('./static/workflow_edit.html', import.meta.url), 'utf8');
  assert.match(css, /\.read_terminal_queue-symbol\s*\{[^}]*background:\s*#13775a\s*;/);
  assert.match(html, /class="node-symbol read_terminal_queue-symbol"/);
});

test('compact terminal input card leaves equal clearance above and below its ports', () => {
  const previousDocument = globalThis.document;
  const previousFrame = globalThis.requestAnimationFrame;
  const previousNodes = state.nodes;
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
  const makeElement = () => {
    const classes = new Set();
    return {
      children: [], dataset: {}, classes,
      classList: { add(...names) { names.forEach((name) => classes.add(name)); } },
      addEventListener() {}, setAttribute() {},
      append(...children) { this.children.push(...children); },
      replaceChildren(...children) { this.children = children; },
      querySelector(selector) { return this.labels[selector]; },
      querySelectorAll(selector) {
        return this.children.filter((child) => child.className === selector.slice(1))
          .concat(this.children.flatMap((child) => child.querySelectorAll(selector)));
      },
      set innerHTML(value) { this.labels = { strong: {}, small: {} }; },
      offsetLeft: 0, offsetTop: 0, offsetWidth: 190, offsetHeight: 104,
    };
  };
  const declarationsFor = (element) => {
    const rule = rules.find((entry) => [...element.classes].some((name) => entry.selector === `.${name}.${name} {}`));
    assert.ok(rule, 'runtime style exists');
    return rule.declarations;
  };
  globalThis.document = {
    styleSheets: [sheet], querySelectorAll: () => [{ href: '/css/workflow.css', sheet }],
    createElement: makeElement, addEventListener() {},
  };
  globalThis.requestAnimationFrame = () => {};
  try {
    const node = createNode('read_terminal_queue', [], { x: 100, y: 100 });
    state.nodes = [node];
    const nodeLayer = makeElement();
    const editor = createWorkflowEditor({ canvas: makeElement(), nodeLayer,
      connectionLayer: makeElement(), nodeCount: {} }, () => {});
    editor.renderNodes();
    assert.equal(nodeLayer.children.length, 1);
    const card = nodeLayer.children[0];
    const body = card.children.find((child) => child.className === 'flow-node-body');
    assert.equal(body.children.length, portsForNode(node).length);
    const bodyHeight = parseFloat(declarationsFor(body).get('height'));
    const portTops = body.children.map((port) => parseFloat(declarationsFor(port).get('top')));
    const topInset = Math.min(...portTops);
    const bottomInset = bodyHeight - Math.max(...portTops) - 12;
    assert.equal(bodyHeight, 56);
    assert.equal(topInset, 8);
    assert.equal(bottomInset, topInset);
    assert.deepEqual(body.children.map((port) => port.dataset.portId), ['control-in', 'control-out', 'list-out']);
    const css = readFileSync(new URL('./static/css/workflow/canvas.css', import.meta.url), 'utf8');
    assert.match(css, /\.flow-node\.read_terminal_queue\s*\{[^}]*min-height:\s*104px/);
  } finally {
    state.nodes = previousNodes;
    if (previousDocument === undefined) delete globalThis.document;
    else globalThis.document = previousDocument;
    if (previousFrame === undefined) delete globalThis.requestAnimationFrame;
    else globalThis.requestAnimationFrame = previousFrame;
  }
});
