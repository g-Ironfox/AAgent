import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import vm from 'node:vm';
import * as data from './static/scheduler-data.mjs';
const { buildSegments, timestamp, isPrecise, matches, formatDuration } = data;
const start = Date.parse('2026-11-19T00:00:00Z');
const at = seconds => new Date(start + seconds * 1000).toISOString();
const event = (kind, seconds, status, extra = {}) => ({ event: kind, timestamp: at(seconds), status, ...extra });
const process = {
  process_id: 'root', workflow_name: 'Root.flow', process_type: 'workflow', status: 'completed', start_time: at(0), finished_at: at(10),
  events: [event('created', 0, 'ready'), event('started', 1, 'running', { dispatch: true }),
    event('yielded', 2, 'ready'), event('resumed', 3, 'running', { dispatch: true }),
    event('blocked', 4, 'blocked', { wait_for: { kind: 'process_exit', process_id: 'child' } }),
    event('woken', 7, 'ready'), event('resumed', 8, 'running', { dispatch: true }), event('completed', 10, 'completed')],
};
let segments = buildSegments(process, start, start + 20000);
assert.deepEqual(segments.map(s => s.status), ['ready', 'running', 'ready', 'running', 'blocked', 'ready', 'running', 'completed']);
assert.equal(segments.reduce((sum, s) => sum + s.end - s.start, 0), 10000);
assert.equal(segments[4].wait.process_id, 'child');
assert.equal(segments.at(-1).point, true);
segments = buildSegments(process, start + 4500, start + 8500);
assert.deepEqual(segments.map(s => s.status), ['blocked', 'ready', 'running']);
assert.equal(segments[0].start, start + 4500);
assert.equal(segments.at(-1).end, start + 8500);
assert.equal(segments.reduce((sum, s) => sum + s.end - s.start, 0), 4000);
assert.equal(buildSegments(process, start + 11000, start + 20000).length, 0);
const lost = { start_time: at(0), status: 'lost', finished_at: at(5),
  events: [event('started', 1, 'running'), event('lost', 5, 'lost')] };
assert.equal(data.finalStatuses.has('lost'), true);
assert.equal(data.statusLabels.lost, '运行状态丢失');
assert.deepEqual(buildSegments(lost, start, start + 20000).map(s => s.status), ['unknown', 'running', 'lost']);
assert.equal(buildSegments(lost, start, start + 20000).at(-1).start, start + 5000);
assert.equal(buildSegments(lost, start + 6000, start + 20000).length, 0);
assert.deepEqual(buildSegments({ ...lost, events: [] }, start, start + 20000).map(s => s.status), ['unknown', 'lost']);
const noEvents = { start_time: at(0), status: 'failed', finished_at: at(5), events: [] };
assert.deepEqual(buildSegments(noEvents, start, start + 10000).map(s => s.status), ['unknown', 'failed']);
assert.equal(isPrecise({ events: [event('started', 0, 'running'), event('resumed', 2, 'running', { dispatch: true })] }), false);
assert.equal(isPrecise(noEvents), false); assert.equal(isPrecise(process), true);
assert.equal(buildSegments({ status: 'blocked' }, start, start + 10000).length, 0);
assert.equal(timestamp(null), null); assert.equal(timestamp('garbage'), null);
assert.equal(buildSegments(process, start, start).length, 0);
const unsorted = { ...process, events: [...process.events].reverse() };
assert.deepEqual(buildSegments(unsorted, start, start + 20000).map(s => s.status), ['ready', 'running', 'ready', 'running', 'blocked', 'ready', 'running', 'completed']);
const tied = { start_time: at(0), events: [event('created', 0, 'ready'), event('started', 0, 'running'), event('blocked', 0, 'blocked')] };
assert.deepEqual(buildSegments(tied, start, start + 10000).map(s => s.status), ['blocked']);
assert.equal(matches(process, { status: 'blocked' }), false); assert.equal(matches(process, { search: 'ROOT.FLOW' }), true);
assert.equal(formatDuration(null), '—');

// Exercise the actual page controller with a small DOM and deterministic transport.
class Element {
  constructor(tag = 'div') { this.tagName = tag; this.children = []; this.listeners = {}; this.style = {}; this.attributes = {}; this.hidden = false; this.value = ''; this._text = ''; this.classList = { toggle: (name, enabled) => { const classes = new Set((this.className || '').split(' ').filter(Boolean)); if (enabled) classes.add(name); else classes.delete(name); this.className = [...classes].join(' '); } }; }
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this.children = children; this._text = ''; }
  set textContent(value) { this._text = String(value); this.children = []; }
  get textContent() { return this._text + this.children.map(child => child.textContent).join(''); }
  addEventListener(kind, callback) { this.listeners[kind] = callback; }
  setAttribute(key, value) { this.attributes[key] = value; }
  querySelector(selector) { return this.children.find(child => child.className?.split(' ').includes(selector.slice(1))) || null; }
  scrollIntoView() { throw new Error('Selecting a process must not scroll the page'); }
  focus() { this.focused = true; }
}
const ids = ['lastRefresh','pauseButton','refreshState','refreshButton','summary','range','customRange','startTime','endTime','applyRange','typeFilter','statusFilter','searchInput','interval','warning','limits','gantt','timeWindow','timelineCount','timelineNote','processTable','tableTabs','tableEmpty','tableCount','details','detailContent','processTablePanel','processTableTab','processDetailsTab'];
const elements = Object.fromEntries(ids.map(id => [id, new Element()]));
const pauseIcon = new Element('span'); pauseIcon.className = 'pause-icon'; elements.pauseButton.append(pauseIcon);
const timers = new Map(); let nextTimer = 1, fetchCount = 0;
for (const status of ['all','ready','running','blocked','waiting_for_input']) { const button = new Element('button'); button.dataset = { table: status }; elements.tableTabs.append(button); }
elements.range.value = '900000'; elements.typeFilter.value = 'all'; elements.statusFilter.value = 'all'; elements.interval.value = '0';
let fail = false;
const active = { process_id: 'child', parent_process_id: 'root', workflow_name: '<img onerror=bad>', process_type: 'workflow', status: 'blocked', start_time: at(-100), observed_at: at(11), events: [event('blocked', 4, 'blocked')], wait_for: { kind: 'terminal_message', process_id: 'terminal' }, active_duration_ms: 20 };
const body = { items: [process], active_items: [active], start: at(0), end: at(12), fetched_at: at(12), active_count: 1, history_count: 2 };
const context = vm.createContext({ ...data, URLSearchParams, AbortController, console,
  setTimeout: (callback, delay) => { const id = nextTimer++; timers.set(id, { callback, delay }); return id; }, clearTimeout: id => timers.delete(id),
  document: { getElementById: id => elements[id], createElement: tag => new Element(tag) },
  fetch: async url => { fetchCount++; assert.match(url, /^\/api\/scheduler\?/); return { ok: !fail, status: fail ? 503 : 200, json: async () => fail ? { error: 'offline' } : body }; },
});
const source = (await readFile(new URL('./static/scheduler.js', import.meta.url), 'utf8')).split('\n').slice(1).join('\n');
vm.runInContext(source, context);
await new Promise(resolve => setImmediate(resolve));
assert.equal(elements.processTable.children.length, 1);
assert.match(elements.processTable.textContent, /<img onerror=bad>/);
assert.match(elements.tableCount.textContent, /1 \/ 1/);
assert.equal(elements.gantt.children.length, 2); // history stays independent from the public current table
assert.match(elements.summary.textContent, /当前活跃进程1/);
elements.typeFilter.value = 'terminal'; elements.typeFilter.listeners.change();
assert.equal(elements.processTable.children.length, 0); assert.equal(elements.tableEmpty.hidden, false);
elements.typeFilter.value = 'all'; elements.statusFilter.value = 'completed'; elements.statusFilter.listeners.change();
assert.equal(elements.processTable.children.length, 0); assert.equal(elements.gantt.children.length, 2);
elements.statusFilter.value = 'all'; elements.searchInput.value = 'terminal'; elements.searchInput.listeners.input();
assert.equal(elements.processTable.children.length, 1); assert.equal(elements.gantt.children.length, 1);
elements.processTable.children[0].children[0].children[0].listeners.click();
assert.equal(elements.details.hidden, false); assert.match(elements.detailContent.textContent, /child/);
assert.equal(elements.processTablePanel.hidden, true);
assert.equal(elements.processDetailsTab.attributes['aria-selected'], 'true');
assert.equal(elements.processTableTab.tabIndex, -1);
const historyPanel = elements.detailContent.children.find(child => child.tagName === 'details');
assert.equal(historyPanel.open, true);
assert.equal(historyPanel.children[1].tagName, 'ol');
assert.match(historyPanel.textContent, /挂起/);
historyPanel.open = false;
await vm.runInContext('refresh()', context);
assert.equal(elements.detailContent.children.find(child => child.tagName === 'details').open, false);

elements.processTableTab.listeners.click();
assert.equal(elements.details.hidden, true);
assert.equal(elements.processTablePanel.hidden, false);
assert.equal(elements.processTableTab.attributes['aria-selected'], 'true');
elements.processDetailsTab.listeners.click();
assert.equal(elements.details.hidden, false);
assert.match(elements.detailContent.textContent, /child/);
await vm.runInContext('refresh()', context);
assert.equal(elements.details.hidden, false); // refresh does not change the selected tab
assert.match(elements.detailContent.textContent, /child/);
let prevented = false;
elements.processDetailsTab.listeners.keydown({ key: 'ArrowLeft', preventDefault() { prevented = true; } });
assert.equal(prevented, true);
assert.equal(elements.processTablePanel.hidden, false);
assert.equal(elements.processTableTab.focused, true);
elements.processTableTab.listeners.keydown({ key: 'End', preventDefault() {} });
assert.equal(elements.details.hidden, false);
elements.processTableTab.listeners.click();
elements.searchInput.value = ''; elements.searchInput.listeners.input();
fail = true; await vm.runInContext('refresh()', context);
assert.equal(elements.warning.hidden, false); assert.match(elements.warning.textContent, /offline/);
assert.equal(elements.processTable.children.length, 1); assert.equal(elements.refreshButton.disabled, false);
elements.range.value = 'custom'; elements.range.listeners.change();
assert.equal(elements.customRange.hidden, false);
elements.startTime.value = '2026-11-20T00:00:00'; elements.endTime.value = '2026-11-19T00:00:00'; elements.applyRange.listeners.click();
assert.match(elements.warning.textContent, /有效的本地时间范围/);
// Public tables are independent from history and preserve next-to-run ordering.
fail = false;
const queuedA = { ...active, process_id: 'queued-a', status: 'ready', workflow_name: 'A.flow', wait_for: null };
const queuedB = { ...active, process_id: 'queued-b', status: 'ready', workflow_name: 'B.flow', wait_for: null };
body.active_items = [active, queuedA, queuedB]; body.active_count = 3;
body.status_counts = { ready: 2, blocked: 1 }; body.process_tables = { ready: ['queued-b','queued-a'], blocked: ['child'], running: [], waiting_for_input: [] };
body.current_available = true; body.history_available = true; body.warnings = [];
elements.range.value = '900000';
await vm.runInContext('refresh()', context);
elements.tableTabs.children[1].listeners.click();
assert.equal(elements.processTable.children.length, 2);
assert.match(elements.processTable.children[0].textContent, /queued-b/);
assert.match(elements.processTable.children[0].textContent, /就绪队列第 1 位/);
assert.equal(elements.tableTabs.children[1].attributes['aria-pressed'], 'true');
elements.tableTabs.children[3].listeners.click();
assert.equal(elements.processTable.children.length, 1); assert.match(elements.processTable.textContent, /child/);
elements.tableTabs.children[0].listeners.click();
assert.equal(elements.processTable.children.length, 3);
body.items = []; body.history_available = false; body.warnings = ['MongoDB 历史日志不可用'];
await vm.runInContext('refresh()', context);
assert.equal(elements.processTable.children.length, 3); assert.match(elements.gantt.textContent, /历史日志不可用/);
assert.equal(elements.warning.hidden, false); assert.match(elements.warning.textContent, /MongoDB/);
body.current_available = false; body.history_available = true; body.items = [process]; body.active_items = []; body.warnings = ['公开 Redis 进程状态不可用'];
await vm.runInContext('refresh()', context);
assert.match(elements.tableEmpty.textContent, /公开 Redis/);
assert.match(elements.summary.textContent, /—/);
assert.equal(elements.gantt.children.length, 2);
// Historical rows and bars also select details in the shared right-hand panel.
elements.gantt.children[1].children[0].listeners.click();
assert.equal(elements.details.hidden, false);
assert.equal(elements.processTablePanel.hidden, true);
assert.match(elements.detailContent.textContent, /Root.flow/);
elements.processTableTab.listeners.click();
elements.gantt.children[1].children[1].children[0].listeners.click();
assert.equal(elements.details.hidden, false);
assert.match(elements.detailContent.textContent, /Root.flow/);
const savedItems = body.items;
body.items = [];
await vm.runInContext('refresh()', context);
assert.equal(elements.details.hidden, false);
assert.match(elements.detailContent.textContent, /该进程已不在本次快照中/);
assert.match(elements.detailContent.textContent, /Root.flow/);
body.items = savedItems;
elements.processTableTab.listeners.click();
// Navigation controls pause scheduling, preserve manual refresh, and resume immediately.
const syncBefore = elements.lastRefresh.textContent;
assert.ok(syncBefore);
elements.interval.value = '2000'; elements.interval.listeners.change();
assert.equal([...timers.values()].filter(timer => timer.delay === 2000).length, 1);
elements.pauseButton.listeners.click();
assert.equal(timers.size, 0);
assert.equal(elements.pauseButton.attributes['aria-pressed'], 'true');
assert.match(pauseIcon.className, /play/);
assert.equal(elements.refreshState.textContent, '自动刷新已暂停');
elements.interval.value = '5000'; elements.interval.listeners.change();
assert.equal(timers.size, 0);
const countBeforeManual = fetchCount;
await elements.refreshButton.listeners.click();
assert.equal(fetchCount, countBeforeManual + 1);
assert.equal(timers.size, 0);
assert.equal(elements.refreshState.textContent, '自动刷新已暂停');
const countBeforeResume = fetchCount;
elements.pauseButton.listeners.click();
await new Promise(resolve => setImmediate(resolve));
assert.equal(fetchCount, countBeforeResume + 1);
assert.equal(elements.pauseButton.attributes['aria-pressed'], 'false');
assert.equal(pauseIcon.className, 'pause-icon');
assert.equal(elements.refreshState.textContent, '自动刷新已开启');
assert.equal([...timers.values()].filter(timer => timer.delay === 5000).length, 1);
fail = true;
await elements.refreshButton.listeners.click();
assert.equal(elements.lastRefresh.textContent, syncBefore);
assert.equal(elements.refreshState.textContent, '同步失败');
assert.equal([...timers.values()].filter(timer => timer.delay === 5000).length, 1);
// Event rows follow the log presentation, retaining stable order and safe text rendering.
const eventList = vm.runInContext(
  'renderEventList(' + JSON.stringify([
    { event: 'woken', timestamp: at(7), status: 'ready', wait_for: { kind: 'process_exit', process_id: 'child' } },
    { event: 'created', timestamp: at(0), status: 'waiting_for_input' },
    { event: 'blocked', timestamp: at(4), status: 'blocked', wait_for: { kind: 'terminal_message', process_id: 'terminal' } },
    { event: 'failed', timestamp: at(7), status: 'failed', error: '<img onerror=bad>', node_id: 'node-1', reason: '执行失败' },
    { event: 'future_event', timestamp: 'invalid', status: 'future_status' },
  ]) + ')', context);
assert.equal(eventList.tagName, 'ol');
assert.equal(eventList.children.length, 5);
assert.match(eventList.children[0].textContent, /创建.*等待输入/);
assert.match(eventList.children[1].textContent, /等待终端消息 · terminal/);
assert.match(eventList.children[2].textContent, /唤醒.*子进程退出 · child/);
assert.match(eventList.children[3].textContent, /节点 · node-1；原因 · 执行失败/);
assert.equal(eventList.children[3].children.at(-1).textContent, '<img onerror=bad>');
assert.match(eventList.children[4].textContent, /未记录.*future_event.*future_status/);
assert.equal(eventList.children[0].children[0].attributes.datetime, at(0));
assert.equal(eventList.children[4].children[0].attributes.datetime, undefined);
assert.match(vm.runInContext('renderEventList([])', context).textContent, /暂无历史调度事件/);
// Lost records reuse the normal finish time and disappear from later windows.
fail = false;
body.items = [{ ...lost, process_id: 'lost-run', process_type: 'workflow', workflow_name: 'Lost.flow' }];
body.current_available = true; body.active_items = []; body.active_count = 0;
body.status_counts = {}; body.warnings = [];
await vm.runInContext('refresh()', context);
assert.equal(elements.gantt.children.length, 2);
elements.gantt.children[1].children[0].listeners.click();
assert.match(elements.detailContent.textContent, /运行状态丢失/);
assert.match(elements.detailContent.textContent, /结束时间（自检发现）/);
const savedStart = body.start;
body.start = at(6);
await vm.runInContext('refresh()', context);
assert.match(elements.gantt.textContent, /没有符合条件的进程记录/);
body.start = savedStart;
console.log('Scheduler assertions passed: event intervals, clipping, legacy records, filters, current table, details and error recovery.');
