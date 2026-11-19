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
  append(...children) {
    for (const child of children) child.parent = this;
    this.children.push(...children);
  }
  replaceChildren(...children) { this.children = []; this.append(...children); }
  setAttribute() {}
  addEventListener(type, listener) { this.listeners[type] = listener; }
  remove() {
    if (this.parent) this.parent.children = this.parent.children.filter((child) => child !== this);
  }
  focus() {}
  showModal() { this.open = true; }
  close() { this.open = false; }
  scrollTo({ top }) { this.scrollTop = top; }
}

async function harness(items = [], submit = async () => {}, sessions = [{
  terminal_id: 'terminal-1', status: 'open',
}], creation = {}) {
  const elements = new Map();
  const historyRequests = [];
  const document = {
    querySelector(selector) {
      if (!elements.has(selector)) elements.set(selector, new Element());
      return elements.get(selector);
    },
    createElement: (tag) => new Element(tag),
  };
  const context = vm.createContext({
    document,
    fetchTerminalHistory: async (limit, terminalId) => {
      historyRequests.push({ limit, terminalId });
      return { fetched_at: '2026-11-16T00:00:00Z', items };
    },
    fetchTerminalSessions: async () => ({ sessions }),
    submitTerminal: submit,
    fetchProcessWorkflowOptions: creation.options || (async () => ({ items: [] })),
    createProcess: creation.submit || (async () => {}),
    crypto: { randomUUID: () => 'generated-terminal' },
    createAutoRefresh: () => ({ schedule() {} }),
  });
  vm.runInContext(source, context);
  await vm.runInContext('refreshStatus()', context);
  while (vm.runInContext('state.loading', context)) await Promise.resolve();
  return { get: (selector) => elements.get(selector), context, historyRequests };
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
  const h = await harness([], async (...args) => {
    sent.push(args);
    return { message: input };
  });
  h.get('#messageInput').value = '  你好  ';
  await vm.runInContext('sendMessage()', h.context);
  assert.deepEqual(sent, [['你好', 'terminal-1']]);
  assert.equal(h.get('#messageList').children[0].dataset.id, '1');
  assert.equal(h.get('#messageInput').value, '');
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
  assert.equal(h.get('#messageList').children.filter((child) => child.dataset.id).length, 0);
  assert.equal(h.get('#sendStatus').textContent, 'storage offline');
});

test('loads available process terminals and reloads history after switching', async () => {
  const sessions = [
    { terminal_id: 'terminal-1', status: 'open' },
    { terminal_id: 'terminal-2', status: 'open' },
  ];
  const h = await harness([], async () => ({}), sessions);
  const select = h.get('#terminalSelect');
  assert.equal(select.children.length, 2);
  assert.equal(select.value, 'terminal-1');
  assert.equal(h.historyRequests.at(-1).terminalId, 'terminal-1');

  select.value = 'terminal-2';
  select.listeners.change();
  while (vm.runInContext('state.loading', h.context)) await Promise.resolve();
  assert.equal(h.historyRequests.at(-1).terminalId, 'terminal-2');
  assert.equal(h.get('#terminalTitle').textContent, '进程终端 · terminal');
});

test('sends a message to the selected process terminal', async () => {
  const sent = [];
  const sessions = [
    { terminal_id: 'terminal-1', status: 'open' },
  ];
  const h = await harness([], async (...args) => {
    sent.push(args);
    return { message: input };
  }, sessions);
  h.get('#messageInput').value = 'hello';
  await vm.runInContext('sendMessage()', h.context);
  assert.deepEqual(sent, [['hello', 'terminal-1']]);
});


test('closed terminals stay readable but cannot send', async () => {
  let sends = 0;
  const sessions = [
    { terminal_id: 'terminal-1', status: 'closed' },
  ];
  const h = await harness([], async () => { sends += 1; }, sessions);
  h.get('#terminalSelect').value = 'terminal-1';
  h.get('#terminalSelect').listeners.change();
  while (vm.runInContext('state.loading', h.context)) await Promise.resolve();
  assert.equal(h.historyRequests.at(-1).terminalId, 'terminal-1');
  assert.equal(h.get('#messageInput').disabled, true);
  assert.equal(h.get('#sendButton').disabled, true);
  h.get('#messageInput').value = 'not allowed';
  await vm.runInContext('sendMessage()', h.context);
  assert.equal(sends, 0);
});

test('switching terminals keeps separate drafts', async () => {
  const sessions = [
    { terminal_id: 'terminal-1', status: 'open' },
    { terminal_id: 'terminal-2', status: 'open' },
  ];
  const h = await harness([], async () => {}, sessions);
  h.get('#messageInput').value = 'draft for first';
  h.get('#terminalSelect').value = 'terminal-2';
  h.get('#terminalSelect').listeners.change();
  while (vm.runInContext('state.loading', h.context)) await Promise.resolve();
  assert.equal(h.get('#messageInput').value, '');
  h.get('#messageInput').value = 'draft for second';
  h.get('#terminalSelect').value = 'terminal-1';
  h.get('#terminalSelect').listeners.change();
  while (vm.runInContext('state.loading', h.context)) await Promise.resolve();
  assert.equal(h.get('#messageInput').value, 'draft for first');
});

test('late history from previous terminal never appears after switching', async () => {
  const sessions = [
    { terminal_id: 'terminal-1', status: 'open' },
    { terminal_id: 'terminal-2', status: 'open' },
  ];
  const h = await harness([], async () => {}, sessions);
  let release;
  h.context.fetchTerminalHistory = async (limit, id) => {
    if (id === 'terminal-1') return new Promise((resolve) => { release = resolve; });
    return { fetched_at: '2026-11-16T00:00:00Z', items: [{ ...output, id: 'new-terminal-message' }] };
  };
  const pendingRefresh = vm.runInContext('refreshStatus()', h.context);
  while (!release) await Promise.resolve();
  h.get('#terminalSelect').value = 'terminal-2';
  h.get('#terminalSelect').listeners.change();
  release({ fetched_at: '2026-11-16T00:00:00Z', items: [input] });
  await pendingRefresh;
  while (vm.runInContext('state.loading', h.context)) await Promise.resolve();
  const rows = h.get('#messageList').children;
  assert.equal(rows.length, 1);
  assert.equal(rows[0].dataset.id, 'new-terminal-message');
});

const workflowOption = {
  file_id: 'workflow-file', name: 'demo.json', input_ports: [{ name: 'text', type: 'content' }],
};

test('create dialog loads workflows and prefills inputs from their declared types', async () => {
  const h = await harness([], undefined, [], {
    options: async () => ({ items: [{ ...workflowOption, input_ports: [
      { name: 'text', type: 'content' },
      { name: 'prompt', type: 'message' },
      { name: 'items', type: 'list-content' },
      { name: 'messages', type: 'list-message' },
      { name: 'values', type: 'map-content' },
    ] }] }),
  });
  await vm.runInContext('openCreateProcess()', h.context);
  assert.equal(h.get('#createProcessDialog').open, true);
  assert.equal(h.get('#processWorkflowSelect').value, 'workflow-file');
  assert.equal(h.get('#processWorkflowSelect').children[0].textContent, 'demo.json');
  assert.deepEqual(JSON.parse(h.get('#processInputs').value), {
    text: '', prompt: { role: 'user', content: '' }, items: [], messages: [], values: {},
  });
  assert.equal(h.get('#submitProcessButton').disabled, false);
});

test('create dialog explains when no workflow is available', async () => {
  const h = await harness();
  await vm.runInContext('openCreateProcess()', h.context);
  assert.equal(h.get('#submitProcessButton').disabled, true);
  assert.match(h.get('#processCreateStatus').textContent, /暂无工作流/);
});

test('creating a process posts inputs and selects its paired terminal', async () => {
  const requests = [];
  const sessions = [];
  const h = await harness([], undefined, sessions, {
    options: async () => ({ items: [workflowOption] }),
    submit: async (file, terminalId, inputs) => {
      requests.push({ file, terminalId, inputs: JSON.parse(JSON.stringify(inputs)) });
      sessions.push({ terminal_id: terminalId, status: 'open' });
      return { terminal_id: terminalId, workflow_name: 'demo.json' };
    },
  });
  await vm.runInContext('openCreateProcess()', h.context);
  h.get('#processInputs').value = '{"text":"hello"}';
  await vm.runInContext('submitNewProcess()', h.context);
  assert.deepEqual(requests, [{ file: 'workflow-file', terminalId: 'generated-terminal', inputs: { text: 'hello' } }]);
  assert.equal(h.get('#terminalSelect').value, 'new-terminal');
  assert.equal(h.get('#createProcessDialog').open, false);
  assert.equal(h.historyRequests.at(-1).terminalId, 'generated-terminal');
  assert.match(h.get('#sendStatus').textContent, /创建请求已排队/);
});

test('invalid creation input is rejected locally without posting', async () => {
  let requests = 0;
  const h = await harness([], undefined, [], { submit: async () => { requests++; } });
  h.get('#processWorkflowSelect').value = 'file';
  for (const value of ['{', '[]', 'null', '42']) {
    h.get('#processInputs').value = value;
    await vm.runInContext('submitNewProcess()', h.context);
  }
  assert.equal(requests, 0);
  assert.match(h.get('#processCreateStatus').textContent, /JSON 对象/);
});

test('failed creation keeps form values and allows retry', async () => {
  const h = await harness([], undefined, [], {
    options: async () => ({ items: [workflowOption] }),
    submit: async () => { throw new Error('Redis unavailable'); },
  });
  await vm.runInContext('openCreateProcess()', h.context);
  h.get('#processInputs').value = '{"text":"draft"}';
  await vm.runInContext('submitNewProcess()', h.context);
  assert.equal(h.get('#createProcessDialog').open, true);
  assert.equal(h.get('#processInputs').value, '{"text":"draft"}');
  assert.equal(h.get('#submitProcessButton').disabled, false);
  assert.equal(h.get('#terminalSelect').disabled, false);
  assert.equal(h.get('#processCreateStatus').textContent, 'Redis unavailable');
});

test('creation timeout warns that the process may already exist', async () => {
  const timeout = new Error('signal is aborted without reason');
  timeout.name = 'AbortError';
  const h = await harness([], undefined, [], {
    options: async () => ({ items: [workflowOption] }),
    submit: async () => { throw timeout; },
  });
  await vm.runInContext('openCreateProcess()', h.context);
  await vm.runInContext('submitNewProcess()', h.context);
  assert.match(h.get('#processCreateStatus').textContent, /请求超时/);
  assert.match(h.get('#processCreateStatus').textContent, /可能已经创建/);
  assert.equal(h.get('#createProcessDialog').open, true);
});

test('repeated submit while creation is pending creates only one process', async () => {
  let requests = 0;
  let reject;
  const h = await harness([], undefined, [], {
    submit: () => { requests++; return new Promise((_, fail) => { reject = fail; }); },
  });
  h.get('#processWorkflowSelect').value = 'file';
  h.get('#processInputs').value = '{}';
  const first = vm.runInContext('submitNewProcess()', h.context);
  await vm.runInContext('submitNewProcess()', h.context);
  assert.equal(requests, 1);
  assert.equal(h.get('#sendButton').disabled, true);
  reject(new Error('offline'));
  await first;
});

test('no process terminals disables sending and never reads global history', async () => {
  let sends = 0;
  const h = await harness([], async () => { sends += 1; }, []);
  assert.equal(h.historyRequests.length, 0);
  assert.equal(h.get('#terminalSelect').children.length, 1);
  assert.equal(h.get('#terminalSelect').children[0].textContent, '暂无进程终端');
  assert.equal(h.get('#messageInput').disabled, true);
  assert.equal(h.get('#sendButton').disabled, true);
  h.get('#messageInput').value = 'hello';
  await vm.runInContext('sendMessage()', h.context);
  assert.equal(sends, 0);
});
