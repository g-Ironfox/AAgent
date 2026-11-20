import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { test } from 'node:test';
import vm from 'node:vm';

const source = await readFile(new URL('./static/workflow.js', import.meta.url), 'utf8');
const html = await readFile(new URL('./static/workflow_edit.html', import.meta.url), 'utf8');
const handlers = ['createMetadataPortRow', 'renderInterfacePortList', 'createFunctionRow',
  'addFunctionStructOptions', 'readFunctions', 'readPortsFromList'].map((name) => {
  const match = source.match(new RegExp('^function ' + name + '\\b[\\s\\S]+?^}', 'm'));
  assert.ok(match, name);
  return match[0];
}).join('\n');

// Model the selectors and events used by the metadata handlers, including template cloning.
class Element {
  constructor(tag, selector = '') {
    this.tag = tag; this.selector = selector; this.children = []; this.dataset = {};
    this.value = ''; this.listeners = {}; this.options = [{ value: 'content' }, { value: 'number' }];
  }
  append(...children) { for (const child of children) { child.parent = this; this.children.push(child); } }
  replaceChildren(...children) { this.children = []; this.append(...children); }
  querySelectorAll(selector) {
    return this.children.flatMap((child) => [
      ...(child.selector === selector || child.tag === selector || selector === '.' + child.className ? [child] : []),
      ...child.querySelectorAll(selector),
    ]);
  }
  querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
  addEventListener(type, callback) { (this.listeners[type] ||= []).push(callback); }
  click() { for (const callback of this.listeners.click || []) callback(); }
  remove() { this.parent.children = this.parent.children.filter((child) => child !== this); }
  add(option) { this.options.push(option); }
  focus() { this.focused = true; }
}
function portRow() {
  const row = new Element('div', '.metadata-port-row');
  row.append(new Element('input', '[data-metadata-port-name]'),
    new Element('select', '[data-metadata-port-type]'), new Element('button', '[data-remove-metadata-port]'));
  return row;
}
function functionRow() {
  const row = new Element('article');
  row.append(...['id', 'name'].map((key) => new Element('input', '[data-function-' + key + ']')),
    new Element('button', '[data-remove-function]'));
  for (const collection of ['input_ports', 'output_ports']) {
    const button = new Element('button', '[data-add-interface-port]');
    button.dataset.addInterfacePort = collection;
    row.append(button, new Element('div', '[data-interface-port-list="' + collection + '"]'));
  }
  return row;
}

test('function metadata independently creates, edits and removes function interfaces', () => {
  const markup = html.split('<template id="functionMetadataTemplate">')[1]?.split('</template>')[0];
  assert.ok(markup, 'dedicated function template exists');
  for (const attribute of ['data-function-id', 'data-function-name', 'data-remove-function']) {
    assert.ok(markup.includes(attribute));
  }
  assert.match(markup, /class="metadata-resource-row function-metadata-row"/);
  assert.equal(markup.includes('subprocess'), false);
  const rows = new Element('div');
  const document = {
    createElement: (tag) => new Element(tag),
    querySelector: (selector) => ({ content: { firstElementChild: {
      cloneNode: selector === '#functionMetadataTemplate' ? functionRow : portRow,
    } } }),
    querySelectorAll: () => rows.children,
  };
  const context = vm.createContext({ document, structDraft: [{ id: 'Record' }],
    Option: class { constructor(text, value) { this.text = text; this.value = value; } } });
  vm.runInContext(handlers, context);
  const row = context.createFunctionRow({ id: 'convert', name: 'Convert',
    input_ports: [{ name: 'record', type: 'struct:Record' }], output_ports: [] });
  rows.append(row);
  const select = row.querySelector('[data-metadata-port-type]');
  assert.equal(select.value, 'struct:Record');
  assert.ok(select.options.some((option) => option.value === 'list-struct:Record'));
  row.querySelector('[data-function-id]').value = ' convert_new ';
  row.querySelector('[data-function-name]').value = ' Updated ';
  row.querySelectorAll('[data-add-interface-port]')[1].click();
  const output = row.querySelector('[data-interface-port-list="output_ports"]');
  assert.equal(output.querySelector('.metadata-empty'), null);
  output.querySelector('input').value = 'answer';
  const outputType = output.querySelector('select');
  assert.ok(outputType.options.some((option) => option.value === 'struct:Record'));
  outputType.value = 'number';
  assert.deepEqual(JSON.parse(JSON.stringify(context.readFunctions())), [{ previous_id: 'convert',
    id: 'convert_new', name: 'Updated', input_ports: [{ name: 'record', type: 'struct:Record' }],
    output_ports: [{ name: 'answer', type: 'number' }] }]);
  output.querySelector('[data-remove-metadata-port]').click();
  assert.equal(context.readFunctions()[0].output_ports.length, 0);
  row.querySelector('[data-remove-function]').click();
  assert.equal(context.readFunctions().length, 0);
});
