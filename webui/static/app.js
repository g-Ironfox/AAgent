import { fetchEvents } from './api.js';
import { eventType, populateTypes, renderTimeline } from './render.js';

const state = { snapshot: null, paused: false, loading: false, timer: null };
const elements = {
  connection: document.querySelector('#connection'), queueName: document.querySelector('#queueName'),
  pendingCount: document.querySelector('#pendingCount'), runningCount: document.querySelector('#runningCount'), doneCount: document.querySelector('#doneCount'),
  workerCard: document.querySelector('#workerCard'), workerState: document.querySelector('#workerState'), workerDetail: document.querySelector('#workerDetail'),
  lastRefresh: document.querySelector('#lastRefresh'), refreshState: document.querySelector('#refreshState'), warningBanner: document.querySelector('#warningBanner'),
  resultCount: document.querySelector('#resultCount'), searchInput: document.querySelector('#searchInput'), typeFilter: document.querySelector('#typeFilter'),
  interval: document.querySelector('#interval'), pauseButton: document.querySelector('#pauseButton'), refreshButton: document.querySelector('#refreshButton'),
  sections: {
    done: { list: document.querySelector('#historyList'), count: document.querySelector('#historyVisibleCount') },
    running: { list: document.querySelector('#runningList'), count: document.querySelector('#runningVisibleCount') },
    pending: { list: document.querySelector('#pendingList'), count: document.querySelector('#pendingVisibleCount') },
  },
};

async function refresh() {
  if (state.loading) return;
  state.loading = true;
  elements.refreshButton.disabled = true;
  try {
    const snapshot = await fetchEvents();
    const oldTypes = state.snapshot ? new Set(state.snapshot.items.map(eventType)) : null;
    const newTypes = new Set(snapshot.items.map(eventType));
    state.snapshot = snapshot;
    const typesChanged = !oldTypes || oldTypes.size !== newTypes.size || [...oldTypes].some((type) => !newTypes.has(type));
    if (typesChanged) populateTypes(elements.typeFilter, snapshot.items);
    renderSnapshot();
    setConnection(true);
  } catch (error) {
    setConnection(false);
    elements.warningBanner.hidden = false;
    elements.warningBanner.textContent = `事件接口不可用：${error.message}${state.snapshot ? '，页面展示最后一次成功快照' : ''}`;
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
    if (selectedType !== 'all' && eventType(item) !== selectedType) return false;
    return !query || JSON.stringify(item.event).toLocaleLowerCase('zh-CN').includes(query);
  });
  const counts = renderTimeline(elements.sections, items, Boolean(query) || selectedType !== 'all');
  elements.resultCount.textContent = `${counts.done + counts.running + counts.pending} 条事件`;
}

function renderWorker(worker) {
  const now = Date.now();
  const updated = worker.updated_at ? new Date(worker.updated_at) : null;
  const updatedAt = updated && !Number.isNaN(updated.getTime()) ? updated : null;
  const started = worker.started_at ? new Date(worker.started_at) : null;
  const startedAt = started && !Number.isNaN(started.getTime()) ? started : null;
  const idleStale = worker.state === 'idle' && (!updatedAt || now - updatedAt.getTime() > 15000);
  const crashed = worker.state === 'processing' && startedAt && now - startedAt.getTime() > 10 * 60 * 1000;
  const stale = idleStale || crashed;
  elements.workerCard.className = `worker-summary ${stale ? 'stale' : worker.state || 'unknown'}`;
  if (crashed) {
    elements.workerState.textContent = '疑似卡死';
    elements.workerDetail.textContent = '单任务运行超过 10 分钟,Worker 可能已崩溃';
  } else if (worker.state === 'processing') {
    const seconds = startedAt ? Math.max(0, Math.floor((now - startedAt.getTime()) / 1000)) : null;
    elements.workerState.textContent = '正在执行';
    elements.workerDetail.textContent = seconds === null ? '开始时间未知' : `已运行 ${formatDuration(seconds)}`;
  } else if (idleStale) {
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