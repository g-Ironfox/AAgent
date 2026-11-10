import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import vm from 'node:vm';
const checks = [];
function test(name, run) { checks.push({ name, run }); }

const source = (await readFile(new URL('./static/bindings.js', import.meta.url), 'utf8'))
  .replace(/^import[\s\S]+?from '\.\/api\.js';/, '');

class Element {
  constructor(tag = '') {
    this.tag = tag;
    this.children = [];
    this.listeners = {};
    this.dataset = {};
    this.value = '';
    this.textContent = '';
    this.classList = { add() {}, remove() {} };
  }
  append(...children) {
    for (const child of children) child.parent = this;
    this.children.push(...children);
  }
  replaceChildren(...children) { this.children = []; this.append(...children); }
  addEventListener(type, listener) { this.listeners[type] = listener; }
  querySelector() { return this.children.find((child) => child.dataset.unavailable); }
  remove() { this.parent.children = this.parent.children.filter((child) => child !== this); }
  focus() {}
  reset() {}
}

async function harness(bindings = [], files = []) {
  const elements = new Map();
  const calls = [];
  const document = {
    querySelector(selector) {
      if (!elements.has(selector)) elements.set(selector, new Element());
      return elements.get(selector);
    },
    createElement(tag) { return new Element(tag); },
  };
  const save = async (id, payload) => {
    calls.push({ id, payload: JSON.parse(JSON.stringify(payload)) });
    return { id: id || 'created', ...payload };
  };
  const context = vm.createContext({
    document, window: { confirm: () => true },
    fetchEventBindings: async () => ({ items: bindings }),
    fetchEventBindingWorkflowOptions: async () => ({ items: files }),
    createEventBinding: (payload) => save(null, payload),
    updateEventBinding: save,
    deleteEventBinding: async () => {},
  });
  vm.runInContext(source, context);
  await new Promise(setImmediate);
  return { elements, calls, get: (selector) => elements.get(selector) };
}

const file = {
  file_id: 'file-1', name: 'workspace-flow.json', workflow_name: 'internal name',
  input_ports: [{ name: 'content', type: 'content' }], output_ports: [],
};

test('file selection previews ports and submits workspace file ID', async () => {
  const h = await harness([], [file]);
  h.get('#newBinding').listeners.click();
  h.get('#eventType').value = ' TERMINAL ';
  h.get('#workflowFile').value = 'file-1';
  h.get('#workflowFile').listeners.change();
  assert.equal(h.get('#contractWorkflowName').textContent, 'workspace-flow.json');
  assert.equal(h.get('#contractInputPorts').children[0].children[0].textContent, 'content');
  await h.get('#bindingForm').listeners.submit({ preventDefault() {} });
  assert.deepEqual(h.calls, [{ id: null, payload: {
    event_type: 'terminal', workflow_file_id: 'file-1', enabled: true,
  } }]);
});

test('editing a binding selects the file by ID and shows its current name', async () => {
  const h = await harness([{
    id: 'binding-1', event_type: 'terminal', workflow_file_id: 'file-1',
    workflow_file_name: 'old-name.json', enabled: true,
  }], [file]);
  const row = h.get('#bindingList').children[0];
  assert.equal(row.children[0].children[1].children[1].textContent, 'workspace-flow.json');
  row.children[0].listeners.click();
  assert.equal(h.get('#workflowFile').value, 'file-1');
  await h.get('#bindingForm').listeners.submit({ preventDefault() {} });
  assert.equal(h.calls[0].id, 'binding-1');
  assert.equal(h.calls[0].payload.workflow_file_id, 'file-1');
});

test('legacy and missing file bindings prompt a new selection', async () => {
  for (const target of [{ workflow_name: 'legacy' }, { workflow_file_id: 'deleted' }]) {
    const h = await harness([{ id: 'binding-1', event_type: 'terminal', ...target }], [file]);
    h.get('#bindingList').children[0].children[0].listeners.click();
    assert.match(h.get('#formStatus').textContent, /重新选择/);
    h.get('#workflowFile').value = 'file-1';
    h.get('#workflowFile').listeners.change();
    assert.equal(h.get('#formStatus').textContent, '');
  }
});

test('an empty workspace disables saving', async () => {
  const h = await harness();
  assert.equal(h.get('#workflowFile').disabled, true);
  assert.equal(h.get('#saveBinding').disabled, true);
});

for (const { name, run } of checks) {
  await run();
  console.log(`PASS ${name}`);
}
