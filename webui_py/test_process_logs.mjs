import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import vm from 'node:vm';

// A small DOM model tests log rendering without a browser or external services.
class Element {
  constructor(tag = 'div') {
    this.tagName = tag; this.children = []; this.parent = null; this.attributes = {};
    this.listeners = {}; this.hidden = false; this.value = ''; this._text = '';
    this.classList = { toggle: (name, enabled) => {
      const classes = new Set((this.className || '').split(' ').filter(Boolean));
      if (enabled) classes.add(name); else classes.delete(name);
      this.className = [...classes].join(' ');
    } };
  }
  set textContent(value) { this._text = String(value); this.children = []; }
  get textContent() { return this._text + this.children.map((child) => child.textContent).join(''); }
  append(...children) { for (const child of children) this.insertBefore(child, null); }
  insertBefore(child, cursor) {
    child.remove();
    const index = cursor ? this.children.indexOf(cursor) : this.children.length;
    assert.ok(index >= 0); this.children.splice(index, 0, child); child.parent = this;
  }
  remove() {
    if (this.parent) this.parent.children.splice(this.parent.children.indexOf(this), 1);
    this.parent = null;
  }
  get firstElementChild() { return this.children[0] || null; }
  get nextElementSibling() { return this.parent?.children[this.parent.children.indexOf(this) + 1] || null; }
  setAttribute(name, value) { this.attributes[name] = value; }
  addEventListener(name, callback) { this.listeners[name] = callback; }
}

const ids = ['logList', 'emptyState', 'warning', 'logCount', 'refreshState', 'statusFilter', 'typeFilter', 'searchInput', 'interval', 'refreshButton'];
const elements = Object.fromEntries(ids.map((id) => [id, new Element()]));
elements.statusFilter.value = 'all'; elements.typeFilter.value = 'all'; elements.interval.value = '0';
const wait = { kind: 'process_exit', process_id: 'child-1' };
let items = [
  { id: 'db-root', process_id: 'root-1', process_type: 'workflow', workflow_name: 'Root.flow', status: 'blocked', start_time: '2026-11-19T00:00:00Z', active_duration_ms: 20,
    wait_for: wait, events: [{ event: 'blocked', timestamp: '2026-11-19T00:00:01Z', status: 'blocked', wait_for: wait }],
    nodes: [{ node_id: 'call', node_type: 'spawn_and_wait_subprocess', status: 'waiting', duration_ms: 5 }] },
  { id: 'db-child', process_id: 'child-1', process_type: 'workflow', workflow_name: 'Child.flow', status: 'running', events: [] },
  { id: 'db-terminal', process_id: 'terminal-1', process_type: 'terminal', status: 'waiting_for_input', events: [] },
];
let fail = false;
const context = vm.createContext({
  document: { querySelector: (selector) => elements[selector.slice(1)], createElement: (tag) => new Element(tag) },
  window: { clearInterval() {}, setInterval() { return 1; } },
  fetch: async (url) => {
    assert.equal(url, '/api/process-logs?limit=200');
    return { ok: !fail, status: fail ? 503 : 200, json: async () => fail ? { error: 'offline' } : { fetched_at: '2026-11-19T00:00:00Z', items: structuredClone(items) } };
  },
});
vm.runInContext(await readFile(new URL('./static/workflow-logs.js', import.meta.url), 'utf8'), context);
await new Promise((resolve) => setImmediate(resolve));
assert.equal(elements.logList.children.length, 3);
assert.equal(elements.logCount.textContent, '3 / 3 个进程');
let root = elements.logList.children[0];
assert.match(root.textContent, /root-1/);
assert.equal(root.children[0].children[1].textContent, '已挂起');
root.children[0].listeners.click();
assert.equal(root.children[1].hidden, false);
assert.match(root.children[1].textContent, /挂起/);
assert.match(root.children[1].textContent, /等待子进程退出/);
assert.match(root.children[1].textContent, /等待子进程/);
assert.equal(root.children[0].attributes['aria-expanded'], 'true');

// Events and nodes share one panel; records without node timestamps stay visible.
const timeline = root.children[1].children.filter((section) => section.className === 'trace-panel');
assert.equal(timeline.length, 1);
assert.equal(timeline[0].children[0].textContent, '执行时间线 (2)');
assert.equal(timeline[0].children[1].children[0].className, 'timeline-row timeline-event');
assert.equal(timeline[0].children[1].children[1].className, 'timeline-row timeline-node');
assert.match(timeline[0].children[1].children[1].textContent, /时间未知/);

// Long-running nodes remain at their start time with wait/wake events between
// their start and finish, while tied timestamps retain execution order.
const combined = vm.runInContext(`timelinePanel([
  {event:'completed', status:'completed', timestamp:'2026-11-19T00:00:06Z'},
  {event:'created', status:'ready', timestamp:'2026-11-19T00:00:00Z'},
  {event:'started', status:'running', timestamp:'2026-11-19T00:00:01Z'},
  {event:'blocked', status:'blocked', timestamp:'2026-11-19T00:00:03Z', wait_for:{kind:'process_exit', process_id:'nested'}},
  {event:'woken', status:'ready', timestamp:'2026-11-19T00:00:04Z', wait_for:{kind:'process_exit', process_id:'nested'}}
], [
  {node_id:'input', status:'completed', started_at:'2026-11-19T00:00:01Z', duration_ms:1},
  {node_id:'call', node_name:'调用子流程', node_type:'spawn_and_wait_subprocess', status:'completed',
   started_at:'2026-11-19T00:00:02Z', finished_at:'2026-11-19T00:00:05Z', duration_ms:10, elapsed_ms:3000, child_process_id:'nested'}
])`, context);
const combinedRows = combined.children[1].children;
assert.deepEqual(combinedRows.map((row) => row.children[1].children[0].textContent),
  ['创建', '开始执行', 'input', '调用子流程call', '挂起', '唤醒', '完成']);
assert.match(combinedRows[3].textContent, /结束于/);
assert.match(combinedRows[3].textContent, /含等待 3.00 s/);
assert.match(combinedRows[3].textContent, /子进程 nested/);
assert.match(combinedRows[3].textContent, /10 ms/);
assert.match(combinedRows[4].textContent, /等待子进程退出/);
assert.match(combinedRows[5].textContent, /子进程退出/);
const completedOrder = combinedRows.map((row) => row.children[0].textContent);
assert.equal(completedOrder[2], vm.runInContext("formatDate('2026-11-19T00:00:01Z')", context));
const legacy = vm.runInContext("timelinePanel([], [{node_id:'old-node', status:'failed', error:'node failure', duration_ms:1}])", context);
assert.match(legacy.textContent, /old-node/);
assert.match(legacy.textContent, /node failure/);
assert.match(legacy.children[1].children[0].className, /trace-failed/);
assert.match(vm.runInContext('timelinePanel([], [])', context).textContent, /尚无执行轨迹/);

// Refreshing unchanged snapshots keeps existing elements and open details.
await vm.runInContext('refresh()', context);
assert.equal(elements.logList.children[0], root);
items[0].status = 'ready'; items[0].wait_for = null;
items[0].events.push({ event: 'woken', timestamp: '2026-11-19T00:00:02Z', status: 'ready', wait_for: wait });
await vm.runInContext('refresh()', context);
root = elements.logList.children[0];
assert.equal(root.children[1].hidden, false);
assert.equal(root.children[0].children[1].textContent, '就绪');
assert.match(root.children[1].textContent, /唤醒/);
assert.equal(root.children[1].children.filter((section) => section.className === 'trace-panel').length, 1);

// Status, process type, IDs and translated event names can all be filtered.
elements.statusFilter.value = 'running'; elements.statusFilter.listeners.change();
assert.equal(elements.logList.children.length, 1); assert.match(elements.logList.textContent, /child-1/);
elements.statusFilter.value = 'all'; elements.typeFilter.value = 'terminal'; elements.typeFilter.listeners.change();
assert.equal(elements.logList.children.length, 1); assert.match(elements.logList.textContent, /终端进程/);
elements.typeFilter.value = 'all'; elements.searchInput.value = '唤醒'; elements.searchInput.listeners.input();
assert.equal(elements.logList.children.length, 1); assert.match(elements.logList.textContent, /root-1/);
elements.searchInput.value = 'missing'; elements.searchInput.listeners.input();
assert.equal(elements.logList.children.length, 0); assert.equal(elements.emptyState.hidden, false);
elements.searchInput.value = ''; elements.searchInput.listeners.input();

// Unknown states and missing dates must never render as completed or epoch time.
assert.equal(vm.runInContext("formatDate(null)", context), '时间未知');
const unknown = vm.runInContext("renderRecord({process_id:'unknown', status:'new_status'})", context);
assert.equal(unknown.children[0].children[1].textContent, 'new_status');

// A failed refresh keeps the last successful list available.
fail = true;
await vm.runInContext('refresh()', context);
assert.equal(elements.warning.hidden, false); assert.match(elements.warning.textContent, /offline/);
assert.equal(elements.logList.children.length, 3);
console.log('Process log UI assertions passed (timeline ordering, states, events, filters, refresh and errors).');
