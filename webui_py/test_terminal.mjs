import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import vm from 'node:vm';

const source = (await readFile(new URL('./static/terminal.js', import.meta.url), 'utf8'))
  .replace(/^import .*;\r?\n/gm, '');

class Element {
  constructor(tag = 'div') {
    this.tagName = tag;
    this.children = [];
    this.dataset = {};
    this.listeners = {};
    this.style = {};
    this.value = '';
    this.scrollHeight = 100;
    this.scrollTop = 0;
    this.clientHeight = 100;
    const classes = new Set();
    this.classList = {
      add: (name) => classes.add(name), remove: (name) => classes.delete(name),
      contains: (name) => classes.has(name),
    };
  }
  append(...children) { this.children.push(...children); }
  addEventListener(type, listener) { this.listeners[type] = listener; }
  remove() {}
  focus() {}
  scrollTo({ top }) { this.scrollTop = top; }
}

async function harness(items = [], submit = async () => {}) {
  const elements = new Map();
  const document = {
    querySelector(selector) {
      if (!elements.has(selector)) elements.set(selector, new Element());
      return elements.get(selector);
    },
    createElement: (tag) => new Element(tag),
  };
  const context = vm.createContext({
    document,
    fetchTerminalHistory: async () => ({ fetched_at: '2026-11-16T00:00:00Z', items }),
    submitTerminal: submit,
    createAutoRefresh: () => ({ schedule() {} }),
  });
  vm.runInContext(source, context);
  await vm.runInContext('refreshStatus()', context);
  await Promise.resolve();
  return { get: (selector) => elements.get(selector), context };
}

const input = { id: '1', role: 'user', content: '你好', created_at: '2026-11-16T00:00:00Z' };
const output = { id: '2', role: 'assistant', content: '<b>输出</b>\n第二行', created_at: '2026-11-16T00:00:01Z' };

test('renders independent message fields as text with input/output authors', async () => {
  const h = await harness([input, output]);
  const rows = h.get('#messageList').children;
  assert.equal(rows.length, 2);
  assert.equal(rows[0].children[0].children[0].textContent, 'TERMINAL');
  assert.equal(rows[1].children[0].children[0].textContent, 'AGENT');
  assert.equal(rows[1].children[1].textContent, '<b>输出</b>\n第二行');
  assert.match(rows[1].className, /response-message/);
});

test('refresh deduplicates messages by stored ID', async () => {
  const h = await harness([input, output]);
  await vm.runInContext('refreshStatus()', h.context);
  await vm.runInContext('refreshStatus()', h.context);
  assert.equal(h.get('#messageList').children.length, 2);
});

test('successful send shows persisted input before a later history refresh', async () => {
  const sent = [];
  const h = await harness([], async (content) => {
    sent.push(content);
    return { queue: 'priority_queue', message: input };
  });
  h.get('#messageInput').value = '  你好  ';
  await vm.runInContext('sendMessage()', h.context);
  assert.deepEqual(sent, ['你好']);
  assert.equal(h.get('#messageList').children[0].dataset.id, '1');
  assert.equal(h.get('#messageInput').value, '');
  assert.equal(h.get('#queueName').textContent, 'priority_queue');
  h.context.items = [input];
  vm.runInContext('appendHistory(items)', h.context);
  assert.equal(h.get('#messageList').children.length, 1);
});

test('failed send preserves draft and does not append a message', async () => {
  const h = await harness([], async () => { throw new Error('storage offline'); });
  h.get('#messageInput').value = 'draft';
  await vm.runInContext('sendMessage()', h.context);
  assert.equal(h.get('#messageInput').value, 'draft');
  assert.equal(h.get('#messageInput').disabled, false);
  assert.equal(h.get('#sendButton').disabled, false);
  assert.equal(h.get('#messageList').children.length, 0);
  assert.equal(h.get('#sendStatus').textContent, 'storage offline');
});
