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
  constructor(tag = 'div') { this.tagName = tag; this.children = []; this.listeners = {}; this.style = {}; this.attributes = {}; this.hidden = false; this.value = ''; this._text = ''; }
  append(...children) { this.children.push(...children); }
  replaceChildren(...children) { this.children = children; this._text = ''; }
  set textContent(value) { this._text = String(value); this.children = []; }
  get textContent() { return this._text + this.children.map(child => child.textContent).join(''); }
  addEventListener(kind, callback) { this.listeners[kind] = callback; }
  setAttribute(key, value) { this.attributes[key] = value; }
  scrollIntoView() {}
}
const ids = ['refreshState','refreshButton','summary','range','customRange','startTime','endTime','applyRange','typeFilter','statusFilter','searchInput','interval','warning','limits','gantt','timeWindow','timelineCount','timelineNote','processTable','tableEmpty','tableCount','details','detailContent','closeDetails'];
const elements = Object.fromEntries(ids.map(id => [id, new Element()]));
elements.range.value = '900000'; elements.typeFilter.value = 'all'; elements.statusFilter.value = 'all'; elements.interval.value = '0';
let fail = false;
const active = { process_id: 'child', parent_process_id: 'root', workflow_name: '<img onerror=bad>', process_type: 'workflow', status: 'blocked', start_time: at(-100), observed_at: at(11), events: [event('blocked', 4, 'blocked')], wait_for: { kind: 'terminal_message', process_id: 'terminal' }, active_duration_ms: 20 };
const body = { items: [process], active_items: [active], start: at(0), end: at(12), fetched_at: at(12), active_count: 1, history_count: 2 };
const context = vm.createContext({ ...data, URLSearchParams, AbortController, console,
  setTimeout: () => 1, clearTimeout() {},
  document: { getElementById: id => elements[id], createElement: tag => new Element(tag) },
  fetch: async url => { assert.match(url, /^\/api\/scheduler\?/); return { ok: !fail, status: fail ? 503 : 200, json: async () => fail ? { error: 'offline' } : body }; },
});
const source = (await readFile(new URL('./static/scheduler.js', import.meta.url), 'utf8')).split('\n').slice(1).join('\n');
vm.runInContext(source, context);
await new Promise(resolve => setImmediate(resolve));
assert.equal(elements.processTable.children.length, 1);
assert.match(elements.processTable.textContent, /<img onerror=bad>/);
assert.match(elements.tableCount.textContent, /1 \/ 1/);
assert.equal(elements.gantt.children.length, 3); // axis + history + independently loaded active process
assert.match(elements.summary.textContent, /当前活跃进程1/);
elements.typeFilter.value = 'terminal'; elements.typeFilter.listeners.change();
assert.equal(elements.processTable.children.length, 0); assert.equal(elements.tableEmpty.hidden, false);
elements.typeFilter.value = 'all'; elements.statusFilter.value = 'completed'; elements.statusFilter.listeners.change();
assert.equal(elements.processTable.children.length, 0); assert.equal(elements.gantt.children.length, 2);
elements.statusFilter.value = 'all'; elements.searchInput.value = 'terminal'; elements.searchInput.listeners.input();
assert.equal(elements.processTable.children.length, 1); assert.equal(elements.gantt.children.length, 2);
elements.processTable.children[0].children[0].children[0].listeners.click();
assert.equal(elements.details.hidden, false); assert.match(elements.detailContent.textContent, /child/);
elements.closeDetails.listeners.click(); assert.equal(elements.details.hidden, true);
elements.searchInput.value = ''; elements.searchInput.listeners.input();
fail = true; await vm.runInContext('refresh()', context);
assert.equal(elements.warning.hidden, false); assert.match(elements.warning.textContent, /offline/);
assert.equal(elements.processTable.children.length, 1); assert.equal(elements.refreshButton.disabled, false);
elements.range.value = 'custom'; elements.range.listeners.change();
assert.equal(elements.customRange.hidden, false);
elements.startTime.value = '2026-11-20T00:00:00'; elements.endTime.value = '2026-11-19T00:00:00'; elements.applyRange.listeners.click();
assert.match(elements.warning.textContent, /有效的本地时间范围/);
console.log('Scheduler assertions passed: event intervals, clipping, legacy records, filters, current table, details and error recovery.');
