import { fetchEvents } from './api.js';
import { eventType, eventPreview, eventTime, populateTypes, renderEvents } from './render.js';

const state = { snapshot: null, filter: 'all', paused: false, loading: false, timer: null, listSignature: '' };
const elements = {
  connection: document.querySelector('#connection'), queueName: document.querySelector('#queueName'),
  pendingCount: document.querySelector('#pendingCount'), runningCount: document.querySelector('#runningCount'), doneCount: document.querySelector('#doneCount'),
  workerCard: document.querySelector('#workerCard'), workerState: document.querySelector('#workerState'), workerDetail: document.querySelector('#workerDetail'),
  lastRefresh: document.querySelector('#lastRefresh'), refreshState: document.querySelector('#refreshState'), warningBanner: document.querySelector('#warningBanner'),
  eventList: document.querySelector('#eventList'), resultCount: document.querySelector('#resultCount'), searchInput: document.querySelector('#searchInput'), typeFilter: document.querySelector('#typeFilter'),
  interval: document.querySelector('#interval'), pauseButton: document.querySelector('#pauseButton'), refreshButton: document.querySelector('#refreshButton'),
};

async function refresh() {
  if (state.loading) return;
  state.loading = true;
  elements.refreshButton.disabled = true;
  try {
    const snapshot = await fetchEvents();
    const oldTypes = state.snapshot ? state.snapshot.items.map(eventType).join('|') : '';
    const newTypes = snapshot.items.map(eventType).join('|');
    state.snapshot = snapshot;
    if (oldTypes !== newTypes) populateTypes(elements.typeFilter, snapshot.items);
    renderSnapshot();
    setConnection(true);
  } catch (error) {
    setConnection(false);
    elements.warningBanner.hidden = false;
    elements.warningBanner.textContent = `事件接口不可用：${error.message}`;
  } finally {
    state.loading = false;
    elements.refreshButton.disabled = false;
    schedule();
  }
}

function renderSnapshot() {
  const snapshot = state.snapshot;
  elements.queueName.textContent = snapshot.queue;
  elements.pendingCount.textContent = Number(snapshot.summary.pending).toLocaleString('zh-CN');
  elements.runningCount.textContent = Number(snapshot.summary.running).toLocaleString('zh-CN');
  elements.doneCount.textContent = Number(snapshot.summary.done).toLocaleString('zh-CN');
  elements.lastRefresh.textContent = new Date(snapshot.fetched_at).toLocaleTimeString('zh-CN', { hour12: false });
  renderWorker(snapshot.worker || {});
  renderWarnings(snapshot.warnings);
  renderFilteredEvents();
}

function renderFilteredEvents() {
  if (!state.snapshot) return;
  const query = elements.searchInput.value.trim().toLocaleLowerCase('zh-CN');
  const selectedType = elements.typeFilter.value;
  const items = state.snapshot.items.filter((item) => {
    if (state.filter !== 'all' && item.status !== state.filter) return false;
    if (selectedType !== 'all' && eventType(item) !== selectedType) return false;
    return !query || JSON.stringify(item.event).toLocaleLowerCase('zh-CN').includes(query);
  });
  const signature = items.map((item) => `${item.id}|${item.status}|${item.position ?? ''}|${eventPreview(item)}|${eventTime(item)}`).join('\u0001');
  if (signature === state.listSignature) return;
  state.listSignature = signature;
  renderEvents(elements.eventList, items);
  elements.resultCount.textContent = `${items.length} 条事件`;
}

function renderWorker(worker) {
  const now = Date.now();
  const updated = worker.updated_at ? new Date(worker.updated_at) : null;
  const updatedAt = updated && !Number.isNaN(updated.getTime()) ? updated : null;
  const stale = worker.state === 'idle' && (!updatedAt || now - updatedAt.getTime() > 15000);
  elements.workerCard.className = `worker-state ${stale ? 'stale' : worker.state || 'unknown'}`;
  if (worker.state === 'processing') {
    const started = worker.started_at ? new Date(worker.started_at) : null;
    const seconds = started && !Number.isNaN(started.getTime()) ? Math.max(0, Math.floor((now - started.getTime()) / 1000)) : null;
    elements.workerState.textContent = '正在执行';
    elements.workerDetail.textContent = seconds === null ? '开始时间未知' : `已运行 ${formatDuration(seconds)}`;
  } else if (stale) {
    elements.workerState.textContent = '疑似离线';
    elements.workerDetail.textContent = '状态超过 15 秒未更新';
  } else if (worker.state === 'idle') {
    elements.workerState.textContent = '等待任务';
    elements.workerDetail.textContent = updatedAt ? `更新于 ${updatedAt.toLocaleTimeString('zh-CN', { hour12: false })}` : '阻塞于 Redis 队列';
  } else {
    elements.workerState.textContent = '尚未上报';
    elements.workerDetail.textContent = 'Worker 状态 Key 不存在';
  }
}

function renderWarnings(warnings) {
  const messages = warnings ? Object.entries(warnings).map(([source, message]) => `${source}: ${message}`) : [];
  elements.warningBanner.hidden = messages.length === 0;
  elements.warningBanner.textContent = messages.join(' · ');
}

function setFilter(filter) {
  state.filter = filter;
  document.querySelectorAll('[data-filter]').forEach((button) => button.classList.toggle('active', button.dataset.filter === filter));
  document.querySelectorAll('[data-summary-filter]').forEach((button) => {
    button.classList.toggle('active', filter !== 'all' && button.dataset.summaryFilter === filter);
  });
  renderFilteredEvents();
}

function setConnection(online) {
  elements.connection.className = `connection ${online ? 'online' : 'offline'}`;
  elements.connection.querySelector('span').textContent = online ? '已同步' : '连接失败';
}

function formatDuration(seconds) {
  if (seconds < 60) return `${seconds}s`;
  return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
}

function schedule() {
  window.clearTimeout(state.timer);
  if (!state.paused) state.timer = window.setTimeout(refresh, Number(elements.interval.value));
}

document.querySelectorAll('[data-filter]').forEach((button) => button.addEventListener('click', () => setFilter(button.dataset.filter)));
document.querySelectorAll('[data-summary-filter]').forEach((button) => button.addEventListener('click', () => setFilter(button.dataset.summaryFilter)));
elements.searchInput.addEventListener('input', renderFilteredEvents);
elements.typeFilter.addEventListener('change', renderFilteredEvents);
elements.interval.addEventListener('change', schedule);
elements.refreshButton.addEventListener('click', refresh);
elements.pauseButton.addEventListener('click', () => {
  state.paused = !state.paused;
  elements.pauseButton.classList.toggle('active', state.paused);
  elements.pauseButton.querySelector('.pause-icon').classList.toggle('play', state.paused);
  elements.pauseButton.title = state.paused ? '继续自动刷新' : '暂停自动刷新';
  elements.pauseButton.setAttribute('aria-label', elements.pauseButton.title);
  elements.refreshState.textContent = state.paused ? '自动刷新已暂停' : '自动刷新已开启';
  schedule();
});

refresh();