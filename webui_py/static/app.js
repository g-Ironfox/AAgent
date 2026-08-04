import { deleteEvent, fetchEvents } from './api.js';
import { createAutoRefresh } from './auto-refresh.js';
import { eventType, populateTypes, renderTimeline, setEventDeleteHandler, syncTypeFilterLabel } from './render.js';
import { captureAnchorState, restoreAnchorState } from './scroll-anchor.js';

const state = { snapshot: null, loading: false, selectedTypes: new Set(), initialPositioned: false, anchorRestoreSuppressedUntil: 0 };
const elements = {
  pendingCount: document.querySelector('#pendingCount'), doneCount: document.querySelector('#doneCount'),
  workerCard: document.querySelector('#workerCard'), workerState: document.querySelector('#workerState'), workerDetail: document.querySelector('#workerDetail'),
  lastRefresh: document.querySelector('#lastRefresh'), refreshState: document.querySelector('#refreshState'), warningBanner: document.querySelector('#warningBanner'),
  resultCount: document.querySelector('#resultCount'), searchInput: document.querySelector('#searchInput'), typeFilter: document.querySelector('#typeFilter'),
  timeline: document.querySelector('.timeline'), runningSection: document.querySelector('#runningSection'),
  runningButton: document.querySelector('#runningButton'),
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
    if (typesChanged) populateTypes(elements.typeFilter, snapshot.items, state.selectedTypes);
    renderSnapshot();
    setConnection(true);
  } catch (error) {
    setConnection(false);
    elements.warningBanner.hidden = false;
    elements.warningBanner.textContent = `事件接口不可用：${error.message}${state.snapshot ? '，页面展示最后一次成功快照' : ''}`;
  } finally {
    state.loading = false;
    elements.refreshButton.disabled = false;
    autoRefresh.schedule();
  }
}

function renderSnapshot() {
  const snapshot = state.snapshot;
  elements.pendingCount.textContent = formatSummaryCount(snapshot.summary.pending, snapshot.sources?.redis === 'ok');
  elements.doneCount.textContent = formatSummaryCount(snapshot.summary.history, snapshot.sources?.mongodb === 'ok');
  elements.lastRefresh.textContent = new Date(snapshot.fetched_at).toLocaleTimeString('zh-CN', { hour12: false });
  renderWorker(snapshot.worker || {});
  renderWarnings(snapshot.warnings);
  elements.runningButton.classList.toggle('has-running', snapshot.items.some((item) => item.status === 'running'));
  renderFilteredEvents();
}

function renderFilteredEvents() {
  if (!state.snapshot) return;
  const query = elements.searchInput.value.trim().toLocaleLowerCase('zh-CN');
  const selectedTypes = state.selectedTypes;
  const items = state.snapshot.items.filter((item) => {
    if (selectedTypes.size > 0 && !selectedTypes.has(eventType(item))) return false;
    return !query || JSON.stringify(item.event).toLocaleLowerCase('zh-CN').includes(query);
  });
  const anchorState = state.initialPositioned ? captureAnchorState(elements.timeline, '.event-row') : null;
  const counts = renderTimeline(elements.sections, items, Boolean(query) || selectedTypes.size > 0, state.snapshot.sources);
  elements.resultCount.textContent = `${counts.done + counts.running + counts.pending} 条事件`;
  if (!state.initialPositioned) {
    elements.timeline.scrollTop = elements.runningSection.offsetTop;
    state.initialPositioned = true;
  } else if (anchorState && Date.now() > state.anchorRestoreSuppressedUntil) {
    window.requestAnimationFrame(() => {
      if (Date.now() > state.anchorRestoreSuppressedUntil) {
        restoreAnchorState(elements.timeline, anchorState, '.event-row');
      }
    });
  }
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
  if (worker.state === 'unavailable') {
    elements.workerState.textContent = '不可用';
    elements.workerDetail.textContent = '无法读取 Worker 状态';
  } else if (worker.state === 'invalid') {
    elements.workerState.textContent = '状态无效';
    elements.workerDetail.textContent = 'Worker 状态数据格式不正确';
  } else if (crashed) {
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

function formatSummaryCount(value, available) {
  return available && Number.isFinite(Number(value)) ? Number(value).toLocaleString('zh-CN') : '--';
}

function renderWarnings(warnings) {
  const messages = warnings ? Object.entries(warnings).map(([source, message]) => `${source}: ${message}`) : [];
  elements.warningBanner.hidden = messages.length === 0;
  elements.warningBanner.textContent = messages.join(' · ');
}

function setConnection(online) {
  elements.lastRefresh.classList.toggle('sync-error', !online);
  if (!online) elements.lastRefresh.textContent = '同步失败';
}

function formatDuration(seconds) {
  if (seconds < 60) return `${seconds}s`;
  return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
}

elements.searchInput.addEventListener('input', renderFilteredEvents);
elements.runningButton.addEventListener('click', () => {
  state.anchorRestoreSuppressedUntil = Date.now() + 1200;
  elements.timeline.scrollTo({ top: elements.runningSection.offsetTop, behavior: 'smooth' });
});

function initTypeFilter() {
  const container = elements.typeFilter;
  const toggle = container.querySelector('.type-filter-toggle');
  const menu = container.querySelector('.type-filter-menu');
  const closeMenu = () => {
    menu.hidden = true;
    toggle.setAttribute('aria-expanded', 'false');
  };
  toggle.addEventListener('click', () => {
    const opening = menu.hidden;
    menu.hidden = !opening;
    toggle.setAttribute('aria-expanded', String(opening));
  });
  document.addEventListener('click', (event) => {
    if (!container.contains(event.target)) closeMenu();
  });
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') closeMenu();
  });
  menu.addEventListener('click', (event) => {
    if (!event.target.closest('.type-filter-clear')) return;
    state.selectedTypes.clear();
    for (const box of menu.querySelectorAll('input[type="checkbox"]')) box.checked = false;
    syncTypeFilterLabel(container, state.selectedTypes);
    renderFilteredEvents();
  });
  menu.addEventListener('change', (event) => {
    const box = event.target;
    if (!(box instanceof HTMLInputElement) || box.type !== 'checkbox') return;
    if (box.checked) state.selectedTypes.add(box.value);
    else state.selectedTypes.delete(box.value);
    syncTypeFilterLabel(container, state.selectedTypes);
    renderFilteredEvents();
  });
}

async function handleDeleteEvent(item) {
  const message = item.status === 'pending'
    ? '确定从等待队列中删除该事件吗？'
    : '确定删除该历史事件吗？删除后不可恢复。';
  if (!window.confirm(message)) return;
  const payload = item.status === 'pending'
    ? { status: 'pending', position: item.position, fingerprint: item.fingerprint }
    : { status: 'done', doc_id: item.doc_id };
  try {
    await deleteEvent(payload);
  } catch (error) {
    elements.warningBanner.hidden = false;
    elements.warningBanner.textContent = `删除失败：${error.message}`;
  } finally {
    refresh();
  }
}

initTypeFilter();
setEventDeleteHandler(handleDeleteEvent);
elements.refreshButton.addEventListener('click', refresh);
const autoRefresh = createAutoRefresh({
  refresh,
  interval: elements.interval,
  pauseButton: elements.pauseButton,
  refreshState: elements.refreshState,
});

refresh();