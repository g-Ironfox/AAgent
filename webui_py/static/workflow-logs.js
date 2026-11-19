async function fetchProcessLogs() {
  const response = await fetch('/api/process-logs?limit=200', { cache: 'no-store' });
  const body = await response.json();
  if (!response.ok) throw new Error(body.error || 'HTTP ' + response.status);
  return body;
}
const elements = {
  list: document.querySelector('#logList'), empty: document.querySelector('#emptyState'), warning: document.querySelector('#warning'),
  count: document.querySelector('#logCount'), state: document.querySelector('#refreshState'), status: document.querySelector('#statusFilter'),
  type: document.querySelector('#typeFilter'), search: document.querySelector('#searchInput'), interval: document.querySelector('#interval'), refresh: document.querySelector('#refreshButton'),
};
let records = [];
let loading = false;
const expandedProcesses = new Set();
const recordViews = new Map();
const statusLabels = {
  ready: '就绪', running: '运行中', blocked: '已挂起', waiting_for_input: '等待输入',
  completed: '已完成', failed: '失败', terminated: '已终止', waiting: '等待子进程',
};
const eventLabels = { resumed: '再次调度', yielded: '返回就绪', created: '创建', started: '开始执行', blocked: '挂起', woken: '唤醒', completed: '完成', failed: '失败', terminated: '终止' };
function waitDescription(waitFor) {
  if (!waitFor) return '';
  const reason = { terminal_message: '等待终端消息', process_exit: '等待子进程退出' }[waitFor.kind] || waitFor.kind || '等待事件';
  return reason + (waitFor.process_id ? ' · ' + waitFor.process_id : '');
}
function eventDescription(event) {
  if (event.event !== 'woken') return waitDescription(event.wait_for);
  const source = event.wait_for || {};
  const reason = { terminal_message: '终端消息到达', process_exit: '子进程退出' }[source.kind] || source.kind || '事件到达';
  return reason + (source.process_id ? ' · ' + source.process_id : '');
}
function searchableText(item) {
  return (JSON.stringify(item) + ' ' + (statusLabels[item.status] || '') + ' ' +
    (item.events || []).map((event) => (eventLabels[event.event] || event.event) + ' ' + eventDescription(event)).join(' ')).toLocaleLowerCase();
}
function render() {
  const query = elements.search.value.trim().toLocaleLowerCase();
  const status = elements.status.value;
  const visible = records.filter((item) => (status === 'all' || item.status === status) && (elements.type.value === 'all' || item.process_type === elements.type.value) && (!query || searchableText(item).includes(query)));
  const timelineScrollPositions = [];
  const views = visible.map((item) => {
    const processId = item.process_id || item.id;
    const content = JSON.stringify(item);
    let view = recordViews.get(processId);
    if (!view || view.content !== content) {
      const previousTimeline = view?.element.querySelector('.trace-list');
      const top = previousTimeline?.scrollTop ?? 0;
      const left = previousTimeline?.scrollLeft ?? 0;
      view = { content, element: renderRecord(item) };
      recordViews.set(processId, view);
      const timeline = view.element.querySelector('.trace-list');
      if (timeline) timelineScrollPositions.push({ timeline, top, left });
    }
    return view.element;
  });
  const visibleViews = new Set(views);
  for (const child of Array.from(elements.list.children)) {
    if (!visibleViews.has(child)) child.remove();
  }
  let cursor = elements.list.firstElementChild;
  for (const view of views) {
    if (view !== cursor) elements.list.insertBefore(view, cursor);
    cursor = view.nextElementSibling;
  }
  // Restore after insertion so the browser can calculate the scrollable area.
  for (const { timeline, top, left } of timelineScrollPositions) {
    timeline.scrollTop = top;
    timeline.scrollLeft = left;
  }
  const processIds = new Set(records.map((item) => item.process_id || item.id));
  for (const processId of recordViews.keys()) {
    if (!processIds.has(processId)) {
      recordViews.delete(processId);
      expandedProcesses.delete(processId);
    }
  }
  elements.empty.hidden = visible.length !== 0;
  elements.count.textContent = visible.length + ' / ' + records.length + ' 个进程';
}
function renderRecord(item) {
  const processId = item.process_id || item.id;
  const expanded = expandedProcesses.has(processId);
  const article = document.createElement('article');
  article.className = 'run-record' + (item.status === 'failed' ? ' is-failed' : '');
  const summary = document.createElement('button'); summary.className = 'run-summary'; summary.type = 'button'; summary.setAttribute('aria-expanded', 'false');
  const workflow = document.createElement('strong'); workflow.className = 'run-name'; workflow.textContent = item.workflow_name || (item.process_type === 'terminal' ? '终端进程' : '未命名工作流');
  const processIdentity = document.createElement('small'); processIdentity.className = 'process-id';
  processIdentity.textContent = (item.process_type === 'terminal' ? 'terminal' : 'workflow') + ' · ' + (item.process_id || item.id);
  workflow.append(processIdentity);
  const badge = document.createElement('span'); badge.className = 'run-status ' + (Object.hasOwn(statusLabels, item.status) ? item.status : 'unknown'); badge.textContent = statusLabels[item.status] || item.status || '状态未知';
  const time = document.createElement('time'); time.textContent = formatDate(item.start_time);
  const duration = document.createElement('span'); duration.className = 'run-duration'; duration.textContent = formatDuration(item.total_duration_ms ?? item.active_duration_ms) + (item.total_duration_ms == null ? ' 活跃' : ' 总计');
  const chevron = document.createElement('span'); chevron.className = 'run-chevron'; chevron.setAttribute('aria-hidden', 'true');
  summary.append(workflow, badge, time, duration, chevron);
  const details = document.createElement('div'); details.className = 'run-details'; details.hidden = true;
  details.hidden = !expanded;
  summary.setAttribute('aria-expanded', String(expanded));
  article.classList.toggle('is-open', expanded);
  details.append(jsonPanel('进程信息', {
    process_id: item.process_id, process_type: item.process_type, parent_process_id: item.parent_process_id,
    root_process_id: item.root_process_id, terminal_id: item.terminal_id, terminal_process_id: item.terminal_process_id,
    start_time: item.start_time, finished_at: item.finished_at, active_duration_ms: item.active_duration_ms,
    total_duration_ms: item.total_duration_ms,
  }));
  if (item.wait_for) details.append(jsonPanel('当前等待 · ' + waitDescription(item.wait_for), item.wait_for));
  details.append(timelinePanel(item.events || [], item.nodes || []));
  if (item.process_type !== 'terminal') details.append(jsonPanel('输入', item.input), jsonPanel('输出', item.output));
  if (item.error) details.append(jsonPanel('错误', item.error));
  summary.addEventListener('click', () => {
    details.hidden = !details.hidden;
    if (details.hidden) expandedProcesses.delete(processId);
    else expandedProcesses.add(processId);
    summary.setAttribute('aria-expanded', String(!details.hidden));
    article.classList.toggle('is-open', !details.hidden);
  });
  article.append(summary, details); return article;
}
function timelineEntries(events, nodes) {
  const entries = [
    // Routine scheduling transitions add noise between node executions.
    ...events.filter((entry) => entry.event !== 'yielded' && entry.event !== 'resumed')
      .map((entry) => ({ kind: 'event', entry, timestamp: entry.timestamp,
      priority: entry.event === 'created' ? -2 : entry.event === 'started' ? -1 : 1 })),
    ...nodes.map((entry, index) => ({ kind: 'node', entry, index, timestamp: entry.started_at, priority: 0 })),
  ];
  const time = (value) => {
    const parsed = value ? new Date(value).getTime() : NaN;
    return Number.isFinite(parsed) ? parsed : Infinity;
  };
  // Nodes stay at their start time even when a later refresh supplies their end time.
  return entries.sort((a, b) => {
    const left = time(a.timestamp), right = time(b.timestamp);
    return (left === right ? 0 : left - right) || a.priority - b.priority;
  });
}
function timelinePanel(events, nodes) {
  const section = document.createElement('section'); section.className = 'trace-panel';
  const entries = timelineEntries(events, nodes);
  const heading = document.createElement('h2'); heading.textContent = '执行时间线 (' + entries.length + ')';
  section.append(heading);
  if (!entries.length) {
    const empty = document.createElement('p'); empty.className = 'timeline-empty'; empty.textContent = '此记录尚无执行轨迹';
    section.append(empty); return section;
  }
  const list = document.createElement('ol'); list.className = 'trace-list';
  for (const item of entries) {
    const entry = item.entry;
    const row = document.createElement('li'); row.className = 'timeline-row timeline-' + item.kind + (entry.status === 'failed' ? ' trace-failed' : '');
    const time = document.createElement('time'); time.className = 'timeline-time'; time.textContent = formatDate(item.timestamp);
    if (item.timestamp) time.setAttribute('datetime', item.timestamp);
    const identity = document.createElement('span'); identity.className = 'trace-identity';
    const label = document.createElement('span'); label.className = 'trace-label';
    const name = document.createElement('strong');
    name.textContent = item.kind === 'event' ? eventLabels[entry.event] || entry.event : entry.node_name || entry.node_id || '(no id)';
    name.title = name.textContent; label.append(name);
    if (item.kind === 'node' && entry.node_name && entry.node_id) {
      const nodeId = document.createElement('span'); nodeId.className = 'trace-node-id'; nodeId.textContent = entry.node_id; nodeId.title = 'ID: ' + entry.node_id;
      label.append(nodeId);
    }
    const type = document.createElement('small'); type.textContent = item.kind === 'event' ? '进程事件' : '节点 #' + (entry.index ?? item.index + 1) + ' · ' + (entry.node_type || 'unknown');
    identity.append(label, type);
    const status = document.createElement('span'); status.className = 'trace-status'; status.textContent = statusLabels[entry.status] || entry.status || '状态未知';
    const duration = document.createElement('span'); duration.className = 'trace-duration'; duration.textContent = item.kind === 'node' ? formatDuration(entry.duration_ms) : '';
    row.append(time, identity, status, duration);
    const descriptions = [];
    if (item.kind === 'event') {
      const reason = eventDescription(entry);
      if (reason) descriptions.push(reason);
    } else {
      if (entry.function_name || entry.function_id) descriptions.push('函数 ' + (entry.function_name || entry.function_id));
      if (entry.function_call_id) descriptions.push('调用 ID ' + entry.function_call_id);
      if (entry.finished_at) descriptions.push('结束于 ' + formatDate(entry.finished_at));
      if (Number.isFinite(entry.elapsed_ms)) descriptions.push('含等待 ' + formatDuration(entry.elapsed_ms));
      if (entry.child_process_id) descriptions.push('子进程 ' + entry.child_process_id);
    }
    if (descriptions.length) {
      const detail = document.createElement('span'); detail.className = 'timeline-detail'; detail.textContent = descriptions.join(' · '); row.append(detail);
    }
    if (entry.error) {
      const error = document.createElement('small'); error.className = 'trace-error'; error.textContent = entry.error; row.append(error);
    }
    list.append(row);
  }
  section.append(list); return section;
}
function jsonPanel(title, value) {
  const section = document.createElement('section'); section.className = 'json-panel';
  const heading = document.createElement('h2'); heading.textContent = title;
  const pre = document.createElement('pre'); pre.textContent = value == null ? 'null' : typeof value === 'string' ? value : JSON.stringify(value, null, 2);
  section.append(heading, pre); return section;
}
function formatDate(value) { if (!value) return '时间未知'; const date = new Date(value); return Number.isNaN(date.getTime()) ? '时间未知' : date.toLocaleString('zh-CN', { hour12: false }); }
function formatDuration(value) { if (!Number.isFinite(value)) return '耗时未知'; return value < 1000 ? value + ' ms' : (value / 1000).toFixed(2) + ' s'; }
async function refresh() {
  if (loading) return;
  loading = true; elements.refresh.disabled = true;
  try {
    const result = await fetchProcessLogs(); records = result.items || [];
    elements.warning.hidden = true;
    elements.state.textContent = '更新于 ' + new Date(result.fetched_at).toLocaleTimeString('zh-CN', { hour12: false }); render();
  } catch (error) { elements.warning.textContent = '日志加载失败：' + error.message; elements.warning.hidden = false; elements.state.textContent = '同步失败'; }
  finally { loading = false; elements.refresh.disabled = false; }
}
elements.status.addEventListener('change', render);
elements.type.addEventListener('change', render);
elements.search.addEventListener('input', render);
elements.refresh.addEventListener('click', refresh);
elements.interval.addEventListener('change', () => { window.clearInterval(window.processLogRefreshTimer); const interval = Number(elements.interval.value); if (interval) window.processLogRefreshTimer = window.setInterval(refresh, interval); });
window.processLogRefreshTimer = window.setInterval(refresh, Number(elements.interval.value));
refresh();
