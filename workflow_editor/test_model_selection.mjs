import assert from 'node:assert/strict';
import { createInspector } from './static/workflow/inspector/inspector.js';
import { state, workflowSnapshot } from './static/workflow/domain/serialization.js';
import { createNode } from './static/workflow/domain/node-contract.js';

// Exercise the real inspector event bindings without requiring a browser.
export function verifyModelSelection() {
  const previousDocument = globalThis.document;
  const previousNodes = state.nodes;
  const fields = new Map();
  const element = (dataset = {}) => ({
    dataset, value: '', textContent: '', children: [], disabled: false, events: {},
    replaceChildren(...children) { this.children = children; },
    addEventListener(name, callback) { this.events[name] = callback; },
    remove() {},
  });
  const mount = {
    replaceChildren() {
      fields.clear();
      fields.set('[data-field="model"]', element({ field: 'model' }));
      for (const selector of ['[data-model-status]', '[data-refresh-models]', '[data-llm-tools]', '[data-think]', '[data-tool-calls]']) fields.set(selector, element());
    },
    querySelector(selector) { return fields.get(selector) || null; },
    querySelectorAll(selector) { return selector === '[data-field]' ? [fields.get('[data-field="model"]')] : []; },
  };
  globalThis.document = {
    createElement: () => element(),
    querySelector: () => ({ content: { cloneNode: () => ({}) } }),
  };
  try {
    const node = createNode('llm', [], { x: 0, y: 0 });
    node.model = 'REPLACE_WITH_MODEL_ID';
    node.tool_calls = false;
    state.nodes = [node];
    let changed = 0;
    let retries = 0;
    const editor = {
      editorState: { selectedId: node.id }, ensureSelection() {},
      setInspectorRenderer() {}, renderNodes() {},
    };
    const inspector = createInspector({ inspectorContent: mount, inspectorTitle: element(), inspectorType: element() }, editor, () => changed++, { reloadModels: () => retries++ });
    inspector.renderInspector();
    assert.equal(fields.get('[data-field="model"]').disabled, true);
    assert.match(fields.get('[data-model-status]').textContent, /加载/);
    inspector.setModelLoadState({ error: '请求超时' });
    assert.match(fields.get('[data-model-status]').textContent, /请求超时/);
    assert.equal(fields.get('[data-refresh-models]').disabled, false);
    fields.get('[data-refresh-models]').events.click();
    assert.equal(retries, 1);
    assert.equal(node.model, 'REPLACE_WITH_MODEL_ID');
    inspector.setModelLoadState({ loading: true });
    assert.equal(fields.get('[data-refresh-models]').disabled, true);
    const models = [
      { id: 'model-one', name: 'First model', model: 'first', enabled: true },
      { id: 'model-two', name: 'Second model', model: 'second', enabled: true },
      { id: 'disabled', name: 'Disabled', model: 'disabled', enabled: false },
    ];
    inspector.setModels(models);
    const select = fields.get('[data-field="model"]');
    assert.equal(select.disabled, false);
    assert.equal(select.value, 'REPLACE_WITH_MODEL_ID');
    assert.deepEqual(select.children.map((option) => option.value), ['REPLACE_WITH_MODEL_ID', 'model-one', 'model-two']);
    assert.equal(changed, 0, 'loading models must preserve the imported placeholder');
    select.value = 'model-two';
    select.events.input();
    select.events.change();
    assert.equal(node.model, 'model-two');
    assert.equal(changed, 1);
    assert.equal(select.value, 'model-two');
    assert.equal(fields.get('[data-model-status]').textContent, '');
    assert.deepEqual(select.children.map((option) => option.value), ['model-one', 'model-two']);
    assert.equal(workflowSnapshot().nodes.find((item) => item.id === node.id).arguments.model, 'model-two');
    inspector.setModelLoadState({ error: '服务暂时不可用' });
    assert.equal(select.disabled, false, 'keep known models available during a failed refresh');
    assert.equal(node.model, 'model-two');
    inspector.setModels([]);
    assert.equal(fields.get('[data-field="model"]').disabled, true);
    assert.match(fields.get('[data-model-status]').textContent, /添加并启用/);
    assert.equal(fields.get('[data-refresh-models]').disabled, false);
    assert.equal(node.model, 'model-two');
  } finally {
    state.nodes = previousNodes;
    globalThis.document = previousDocument;
  }
}

verifyModelSelection();
