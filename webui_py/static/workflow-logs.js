async function fetchWorkflowLogs() {
  const response = await fetch('/api/workflow-logs?limit=200', { cache: 'no-store' });
  const body = await response.json();
  if (!response.ok) throw new Error(body.error || 'HTTP ' + response.status);
  return body;
}
const elements = {
  list: document.querySelector('#logList'), empty: document.querySelector('#emptyState'), warning: document.querySelector('#warning'),
  count: document.querySelector('#logCount'), state: document.querySelector('#refreshState'), status: document.querySelector('#statusFilter'),
  search: document.querySelector('#searchInput'), interval: document.querySelector('#interval'), refresh: document.querySelector('#refreshButton'),
};
let records = [];
let loading = false;
function render() {
  const query = elements.search.value.trim().toLocaleLowerCase();
  const status = elements.status.value;
  const visible = records.filter((item) => (status === 'all' || item.status === status) && (!query || JSON.stringify(item).toLocaleLowerCase().includes(query)));
  elements.list.replaceChildren(...visible.map(renderRecord));
  elements.empty.hidden = visible.length !== 0;
  elements.count.textContent = visible.length + ' / ' + records.length + ' 次运行';
}
function renderRecord(item) {
  const article = document.createElement('article');
  article.className = 'run-record' + (item.status === 'failed' ? ' is-failed' : '');
  const summary = document.createElement('button'); summary.className = 'run-summary'; summary.type = 'button'; summary.setAttribute('aria-expanded', 'false');
  const workflow = document.createElement('strong'); workflow.className = 'run-name'; workflow.textContent = item.workflow_name || '未命名 workflow';
  const badge = document.createElement('span'); badge.className = 'run-status ' + (item.status === 'failed' ? 'failed' : 'completed'); badge.textContent = item.status === 'failed' ? '失败' : '已完成';
  const time = document.createElement('time'); time.textContent = formatDate(item.started_at);
  const duration = document.createElement('span'); duration.className = 'run-duration'; duration.textContent = formatDuration(item.duration_ms);
  const chevron = document.createElement('span'); chevron.className = 'run-chevron'; chevron.setAttribute('aria-hidden', 'true');
  summary.append(workflow, badge, time, duration, chevron);
  const details = document.createElement('div'); details.className = 'run-details'; details.hidden = true;
  details.append(jsonPanel('输入', item.input), jsonPanel('输出', item.output));
  if (item.node_trace?.length) details.append(tracePanel(item.node_trace));
  if (item.error) details.append(jsonPanel('错误', item.error));
  summary.addEventListener('click', () => { details.hidden = !details.hidden; summary.setAttribute('aria-expanded', String(!details.hidden)); article.classList.toggle('is-open', !details.hidden); });
  article.append(summary, details); return article;
}
function tracePanel(trace) {
  const section = document.createElement('section'); section.className = 'trace-panel';
  const heading = document.createElement('h2'); heading.textContent = '节点轨迹 (' + trace.length + ')';
  const list = document.createElement('ol'); list.className = 'trace-list';
  for (const entry of trace) {
    const row = document.createElement('li'); row.className = 'trace-row' + (entry.status === 'failed' ? ' trace-failed' : '');
    const sequence = document.createElement('span'); sequence.className = 'trace-index'; sequence.textContent = String(entry.index);
    const identity = document.createElement('span'); identity.className = 'trace-identity';
    const nodeId = document.createElement('strong'); nodeId.textContent = entry.node_id || '(no id)';
    const nodeType = document.createElement('small'); nodeType.textContent = entry.node_type || 'unknown';
    identity.append(nodeId, nodeType);
    const nodeStatus = document.createElement('span'); nodeStatus.className = 'trace-status';
    nodeStatus.textContent = entry.status === 'failed' ? '失败' : '完成';
    const duration = document.createElement('time'); duration.className = 'trace-duration'; duration.textContent = formatDuration(entry.duration_ms);
    row.append(sequence, identity, nodeStatus, duration);
    if (entry.error) { const error = document.createElement('small'); error.className = 'trace-error'; error.textContent = entry.error; row.append(error); }
    list.append(row);
  }
  section.append(heading, list); return section;
}
function jsonPanel(title, value) {
  const section = document.createElement('section'); section.className = 'json-panel';
  const heading = document.createElement('h2'); heading.textContent = title;
  const pre = document.createElement('pre'); pre.textContent = value == null ? 'null' : typeof value === 'string' ? value : JSON.stringify(value, null, 2);
  section.append(heading, pre); return section;
}
function formatDate(value) { const date = new Date(value); return Number.isNaN(date.getTime()) ? '时间未知' : date.toLocaleString('zh-CN', { hour12: false }); }
function formatDuration(value) { if (!Number.isFinite(value)) return '耗时未知'; return value < 1000 ? value + ' ms' : (value / 1000).toFixed(2) + ' s'; }
async function refresh() {
  if (loading) return;
  loading = true; elements.refresh.disabled = true;
  try {
    const result = await fetchWorkflowLogs(); records = result.items || [];
    elements.warning.hidden = true;
    elements.state.textContent = '更新于 ' + new Date(result.fetched_at).toLocaleTimeString('zh-CN', { hour12: false }); render();
  } catch (error) { elements.warning.textContent = '日志加载失败：' + error.message; elements.warning.hidden = false; elements.state.textContent = '同步失败'; }
  finally { loading = false; elements.refresh.disabled = false; }
}
elements.status.addEventListener('change', render);
elements.search.addEventListener('input', render);
elements.refresh.addEventListener('click', refresh);
elements.interval.addEventListener('change', () => { window.clearInterval(window.workflowLogRefreshTimer); const interval = Number(elements.interval.value); if (interval) window.workflowLogRefreshTimer = window.setInterval(refresh, interval); });
window.workflowLogRefreshTimer = window.setInterval(refresh, Number(elements.interval.value));
refresh();
