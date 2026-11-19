import { finalStatuses, statusLabels, timestamp, formatDuration, waitLabel, matches, buildSegments, isPrecise } from './scheduler-data.mjs';

const el = Object.fromEntries(['refreshState', 'refreshButton', 'summary', 'range', 'customRange', 'startTime', 'endTime', 'applyRange', 'typeFilter', 'statusFilter', 'searchInput', 'interval', 'warning', 'limits', 'gantt', 'timeWindow', 'timelineCount', 'timelineNote', 'processTable', 'tableEmpty', 'tableCount', 'details', 'detailContent', 'closeDetails'].map(id => [id, document.getElementById(id)]));
let snapshot = null, selectedId = null, timer = null, controller = null, requestId = 0;
let customWindow = null;
const dateFormat = new Intl.DateTimeFormat('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false });
const timeFormat = new Intl.DateTimeFormat('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false });
function date(value) { const time = timestamp(value); return time === null ? '未记录' : dateFormat.format(time); }
function node(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined) element.textContent = text;
  return element;
}
function stateClass(status) { return Object.hasOwn(statusLabels, status) ? status : 'unknown'; }
function badge(status) { return node('span', 'badge ' + stateClass(status), statusLabels[status] || status || '未知'); }
function filter() { return { type: el.typeFilter.value, status: el.statusFilter.value, search: el.searchInput.value.trim() }; }
function records() {
  const map = new Map((snapshot?.items || []).map(item => [item.process_id, item]));
  for (const item of snapshot?.active_items || []) map.set(item.process_id, { ...map.get(item.process_id), ...item });
  return map;
}
function name(process) { return process.workflow_name || (process.process_type === 'terminal' ? '终端进程' : '工作流进程'); }
function processButton(process, className = '') {
  const button = node('button', className); button.type = 'button';
  button.append(node('strong', '', name(process)), node('small', '', process.process_id));
  button.title = name(process) + ' · ' + process.process_id;
  button.addEventListener('click', () => { selectedId = process.process_id; renderDetails(); el.details.scrollIntoView({ behavior: 'smooth', block: 'nearest' }); });
  return button;
}
function renderSummary() {
  const items = snapshot.active_items || [];
  const cards = [['', '当前活跃进程', snapshot.active_count], ['running', '运行中', snapshot.status_counts?.running ?? items.filter(p => p.status === 'running').length], ['ready', '就绪', snapshot.status_counts?.ready ?? items.filter(p => p.status === 'ready').length], ['blocked', '已挂起', snapshot.status_counts?.blocked ?? items.filter(p => p.status === 'blocked').length], ['waiting_for_input', '等待输入', snapshot.status_counts?.waiting_for_input ?? items.filter(p => p.status === 'waiting_for_input').length]];
  el.summary.replaceChildren(...cards.map(([status, label, count], index) => {
    const card = node('div', 'summary-card ' + status);
    card.append(node('span', '', label), node('strong', '', snapshot.current_available === false ? '—' : String(count)));
    return card;
  }));
}
function renderTimeline() {
  const start = timestamp(snapshot.start), end = timestamp(snapshot.end), span = end - start;
  const items = (snapshot.items || []).filter(p => {
    const created = timestamp(p.start_time), finished = timestamp(p.finished_at);
    return created !== null && created <= end && (finished === null || finished >= start) && matches(p, filter());
  }).sort((a, b) => timestamp(a.start_time) - timestamp(b.start_time) || a.process_id.localeCompare(b.process_id));
  el.timeWindow.textContent = date(start) + ' — ' + date(end) + ' · 本地时间';
  el.timelineCount.textContent = items.length + ' 个进程';
  if (snapshot.history_available === false) { el.gantt.replaceChildren(node('p', 'empty', '历史日志不可用，当前进程表仍可独立查看')); return; }
  if (!items.length) { el.gantt.replaceChildren(node('p', 'empty', '所选时间范围内没有符合条件的进程记录')); return; }
  const axisRow = node('div', 'axis-row'); axisRow.append(node('div', 'axis-label', '进程 / 工作流'));
  const axis = node('div', 'axis');
  for (let i = 0; i <= 5; i++) { const tick = node('span', 'tick', timeFormat.format(start + span * i / 5)); tick.style.left = (i * 20) + '%'; axis.append(tick); }
  axisRow.append(axis);
  const rows = items.map(process => {
    const row = node('div', 'gantt-row'); row.append(processButton(process, 'gantt-label'));
    const track = node('div', 'track');
    for (const segment of buildSegments(process, start, end)) {
      const bar = node('button', 'segment ' + stateClass(segment.status) + (segment.point ? ' point' : ''));
      bar.type = 'button'; bar.style.left = ((segment.start - start) / span * 100) + '%';
      if (!segment.point) bar.style.width = ((segment.end - segment.start) / span * 100) + '%';
      const label = (statusLabels[segment.status] || segment.status) + ' · ' + date(segment.start) + (segment.point ? '' : ' — ' + date(segment.end) + ' · ' + formatDuration(segment.end - segment.start)) + (segment.wait ? ' · ' + waitLabel(segment.wait) : '');
      bar.title = label; bar.setAttribute('aria-label', name(process) + ' · ' + label);
      bar.addEventListener('click', () => { selectedId = process.process_id; renderDetails(); el.details.scrollIntoView({ behavior: 'smooth', block: 'nearest' }); });
      track.append(bar);
    }
    row.append(track); return row;
  });
  el.gantt.replaceChildren(axisRow, ...rows);
  el.timelineNote.textContent = '色块表示调度状态的持续时间，菱形表示结束事件。悬停可查看时间与等待原因，点击进程可查看详情。' + (items.some(p => p.process_type !== 'terminal' && !isPrecise(p)) ? ' 部分旧记录仅有生命周期事件，无法还原每次调度；斜纹表示未知状态，连续运行色块不代表连续占用执行器。' : '');
}
function renderTable() {
  const order = { running: 0, ready: 1, blocked: 2, waiting_for_input: 3 };
  const items = (snapshot.active_items || []).filter(p => !finalStatuses.has(p.status) && matches(p, filter())).sort((a, b) => (order[a.status] ?? 4) - (order[b.status] ?? 4) || (timestamp(a.start_time) || 0) - (timestamp(b.start_time) || 0));
  el.processTable.replaceChildren(...items.map(process => {
    const row = node('tr'); const identity = node('td'); identity.append(processButton(process));
    const type = node('td', '', process.process_type === 'terminal' ? '终端' : '工作流'); const state = node('td'); state.append(badge(process.status));
    const parent = node('td', 'mono id-cell', process.parent_process_id || '—'); parent.title = process.parent_process_id || '';
    const wait = node('td', 'id-cell', waitLabel(process.wait_for)); wait.title = waitLabel(process.wait_for);
    const observed = node('td', '', date(process.observed_at));
    const observedTime = timestamp(process.observed_at);
    if (observedTime !== null) observed.title = '距本次获取 ' + formatDuration(Math.max(0, timestamp(snapshot.fetched_at) - observedTime)) + '；进程无状态变化时快照时间不会更新';
    row.append(identity, type, state, parent, wait, node('td', '', formatDuration(process.active_duration_ms)), node('td', '', date(process.start_time)), observed);
    return row;
  }));
  el.tableEmpty.hidden = items.length > 0;
  el.tableEmpty.textContent = snapshot.current_available === false ? '公开 Redis 进程投影暂不可用，请确认 Agent 已更新并启动' : '当前没有符合筛选条件的活跃进程';
  el.tableCount.textContent = snapshot.current_available === false ? '状态不可用' : items.length + ' / ' + snapshot.active_count + ' 个活跃进程';
}
function renderDetails() {
  const process = records().get(selectedId);
  el.details.hidden = !process;
  if (!process) return;
  const grid = node('dl', 'detail-grid');
  for (const [label, value] of [['进程 ID', process.process_id], ['名称', name(process)], ['当前状态', statusLabels[process.status] || process.status], ['类型', process.process_type || 'workflow'], ['父进程', process.parent_process_id || '—'], ['根进程', process.root_process_id || '—'], ['终端', process.terminal_id || '—'], ['等待对象', waitLabel(process.wait_for)], ['累计执行', formatDuration(process.active_duration_ms)], ['最近节点', process.current_node_id ?? '—'], ['创建时间', date(process.start_time)], ['结束时间', date(process.finished_at)], ['快照时间', date(process.observed_at)]]) {
    const item = node('div'); item.append(node('dt', '', label), node('dd', '', value)); grid.append(item);
  }
  const events = node('details'); events.open = el.detailContent.children[1]?.open || false; events.append(node('summary', '', '历史调度事件 · ' + (process.events || []).length), node('pre', '', JSON.stringify(process.events || [], null, 2)));
  const link = node('a', '', '打开进程日志'); link.href = '/logs';
  el.detailContent.replaceChildren(grid, events, link);
}
function render() {
  if (!snapshot) return;
  renderSummary(); renderTimeline(); renderTable(); renderDetails();
  const notices = [];
  if (snapshot.history_truncated) notices.push('时间范围内共有 ' + snapshot.history_count + ' 个进程，历史图仅加载最近 500 条；可缩小时间范围。');
  if (snapshot.active_truncated) notices.push('活跃进程超过 1000 条，当前表仅显示前 1000 条；概览计数涵盖所有活跃进程。');
  el.limits.textContent = notices.join(' '); el.limits.hidden = !notices.length;
}
function schedule() {
  clearTimeout(timer);
  const interval = Number(el.interval.value);
  if (interval > 0) timer = setTimeout(refresh, interval);
}
async function refresh() {
  const id = ++requestId;
  clearTimeout(timer); controller?.abort(); controller = new AbortController();
  const now = Date.now();
  const selectedWindow = el.range.value === 'custom' ? customWindow : { start: now - Number(el.range.value), end: now };
  if (!selectedWindow) { el.warning.textContent = '请设置开始和结束时间后点击应用。'; el.warning.hidden = false; schedule(); return; }
  el.refreshButton.disabled = true;
  const params = new URLSearchParams({ start: new Date(selectedWindow.start).toISOString(), end: new Date(selectedWindow.end).toISOString(), limit: '500' });
  const activeController = controller;
  const timeout = setTimeout(() => activeController.abort(), 15000);
  try {
    const response = await fetch('/api/scheduler?' + params, { cache: 'no-store', signal: controller.signal });
    const body = await response.json();
    if (!response.ok) throw new Error(typeof body.error === 'string' ? body.error : '请求失败（' + response.status + '）');
    if (id !== requestId) return;
    snapshot = body; el.warning.textContent = (body.warnings || []).join('；'); el.warning.hidden = !body.warnings?.length;
    el.refreshState.textContent = '获取于 ' + timeFormat.format(timestamp(body.fetched_at));
    render();
  } catch (error) {
    if (id !== requestId) return;
    el.warning.textContent = '调度数据加载失败：' + (error.name === 'AbortError' ? '请求超时' : error.message) + (snapshot ? '。当前保留上次成功获取的数据。' : '');
    el.warning.hidden = false; el.refreshState.textContent = '同步失败';
  } finally {
    clearTimeout(timeout);
    if (id === requestId) { el.refreshButton.disabled = false; schedule(); }
  }
}
for (const element of [el.typeFilter, el.statusFilter]) element.addEventListener('change', render);
el.searchInput.addEventListener('input', render);
el.refreshButton.addEventListener('click', refresh);
el.interval.addEventListener('change', schedule);
el.closeDetails.addEventListener('click', () => { selectedId = null; el.details.hidden = true; });
el.range.addEventListener('change', () => { el.customRange.hidden = el.range.value !== 'custom'; if (el.range.value !== 'custom' || customWindow) refresh(); });
el.applyRange.addEventListener('click', () => {
  const start = timestamp(el.startTime.value), end = timestamp(el.endTime.value);
  if (start === null || end === null || end <= start || end - start > 7 * 86400000 || end > Date.now()) {
    el.warning.textContent = '请选择有效的本地时间范围：开始早于结束、跨度不超过 7 天，且结束时间不晚于现在。'; el.warning.hidden = false; return;
  }
  customWindow = { start, end }; refresh();
});
function localInput(time) { const value = new Date(time); return new Date(time - value.getTimezoneOffset() * 60000).toISOString().slice(0, 19); }
el.startTime.value = localInput(Date.now() - 900000); el.endTime.value = localInput(Date.now());
refresh();
