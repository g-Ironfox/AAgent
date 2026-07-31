const STUCK_PROCESSING_MS = 5 * 60 * 1000;
const STALE_IDLE_MS = 15 * 1000;

const state = {
  queue: null,
  status: null,
  history: [],
  previousDepth: null,
  queueSignature: null,
  historySignature: null,
  historyStatusKey: null,
  paused: false,
  timer: null,
  loading: false,
};

const elements = {
  connection: document.querySelector('#connection'),
  queueName: document.querySelector('#queueName'),
  queueDepth: document.querySelector('#queueDepth'),
  depthDelta: document.querySelector('#depthDelta'),
  loadedCount: document.querySelector('#loadedCount'),
  agentState: document.querySelector('#agentState'),
  agentStateDetail: document.querySelector('#agentStateDetail'),
  lastRefresh: document.querySelector('#lastRefresh'),
  refreshState: document.querySelector('#refreshState'),
  currentTask: document.querySelector('#currentTask'),
  currentTaskTitle: document.querySelector('#currentTaskTitle'),
  currentTaskDuration: document.querySelector('#currentTaskDuration'),
  currentTaskPreview: document.querySelector('#currentTaskPreview'),
  currentTaskDetails: document.querySelector('#currentTaskDetails'),
  currentTaskRaw: document.querySelector('#currentTaskRaw'),
  eventBreakdown: document.querySelector('#eventBreakdown'),
  messageList: document.querySelector('#messageList'),
  resultCount: document.querySelector('#resultCount'),
  searchInput: document.querySelector('#searchInput'),
  historyList: document.querySelector('#historyList'),
  historyResultCount: document.querySelector('#historyResultCount'),
  historySearchInput: document.querySelector('#historySearchInput'),
  interval: document.querySelector('#interval'),
  pauseButton: document.querySelector('#pauseButton'),
  refreshButton: document.querySelector('#refreshButton'),
  errorBanner: document.querySelector('#errorBanner'),
  historyErrorBanner: document.querySelector('#historyErrorBanner'),
};

async function fetchJSON(url) {
  const response = await fetch(url, { cache: 'no-store' });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.error || `HTTP ${response.status}`);
  return body;
}

async function refresh() {
  if (state.loading) return;
  state.loading = true;
  elements.refreshButton.disabled = true;

  const [queueResult, statusResult, historyResult] = await Promise.allSettled([
    fetchJSON('/api/queue?limit=200'),
    fetchJSON('/api/status'),
    fetchJSON('/api/history?limit=100'),
  ]);

  if (queueResult.status === 'fulfilled') {
    const snapshot = queueResult.value;
    const signature = queueSignature(snapshot);
    if (signature !== state.queueSignature) {
      state.previousDepth = state.queue?.length ?? state.previousDepth;
      state.queue = snapshot;
      state.queueSignature = signature;
      renderQueue();
    } else {
      state.queue = snapshot;
    }
    setConnection(true);
    elements.errorBanner.hidden = true;
  } else {
    setConnection(false);
    showError(elements.errorBanner, `无法读取 Redis 队列：${queueResult.reason.message}`);
  }

  if (statusResult.status === 'fulfilled') {
    state.status = statusResult.value;
    renderStatus();
  } else {
    state.status = { state: 'unknown' };
    renderStatus();
    showError(elements.errorBanner, `无法读取 Agent 状态：${statusResult.reason.message}`);
  }

  if (historyResult.status === 'fulfilled') {
    const items = historyResult.value.items || [];
    const signature = historySignature(items);
    const statusKey = state.status?.state ?? 'unknown';
    if (signature !== state.historySignature || statusKey !== state.historyStatusKey) {
      state.history = items;
      state.historySignature = signature;
      state.historyStatusKey = statusKey;
      renderHistory();
      renderBreakdown(items);
      elements.loadedCount.textContent = items.length.toLocaleString('zh-CN');
    }
    elements.historyErrorBanner.hidden = true;
  } else {
    showError(elements.historyErrorBanner, `无法读取 MongoDB 历史：${historyResult.reason.message}`);
  }

  elements.lastRefresh.textContent = new Date().toLocaleTimeString('zh-CN', { hour12: false });
  state.loading = false;
  elements.refreshButton.disabled = false;
  schedule();
}

// 键控增量同步:复用内容未变化的节点,只插入新增、移除消失的条目,
// 避免整表重建导致的闪烁,并保留已展开的 <details> 状态。
const itemKeyByNode = new WeakMap();

function syncList(container, items, keyOf, createNode, updateNode) {
  // 按 key 收集现有节点(同一 key 可多次出现,如重复消息),按 DOM 顺序排队。
  const buckets = new Map();
  for (const child of container.children) {
    const key = itemKeyByNode.get(child);
    if (key == null) continue;
    const bucket = buckets.get(key);
    if (bucket) bucket.push(child);
    else buckets.set(key, [child]);
  }

  const used = new Set();
  let anchor = null;
  // 从尾部向前对齐:内容未变的节点直接复用并原地更新,只有真正新增的才创建。
  for (let i = items.length - 1; i >= 0; i--) {
    const item = items[i];
    const key = keyOf(item);
    const bucket = buckets.get(key);
    const node = bucket && bucket.length ? bucket.shift() : null;
    if (node) {
      updateNode(node, item);
    } else {
      const fresh = createNode(item);
      itemKeyByNode.set(fresh, key);
      used.add(fresh);
      if (fresh.nextSibling !== anchor) container.insertBefore(fresh, anchor);
      anchor = fresh;
      continue;
    }
    used.add(node);
    if (node.nextSibling !== anchor) container.insertBefore(node, anchor);
    anchor = node;
  }

  // 移除不再出现在列表中的旧节点。
  for (const child of [...container.children]) {
    if (!used.has(child)) child.remove();
  }
}

function renderQueue() {
  const snapshot = state.queue;
  elements.queueName.textContent = snapshot.queue;
  elements.queueDepth.textContent = snapshot.length.toLocaleString('zh-CN');
  const delta = state.previousDepth === null ? null : snapshot.length - state.previousDepth;
  elements.depthDelta.textContent = delta === null
    ? '已获取第一份快照'
    : delta === 0 ? '较上次无变化' : `较上次 ${delta > 0 ? '+' : ''}${delta}`;

  const query = elements.searchInput.value.trim().toLocaleLowerCase('zh-CN');
  // Redis 列表尾部是 BRPOP 消费端：倒序展示,使"下一个被消费"的事件排在最上方。
  const items = snapshot.items
    .filter((item) => !query || item.raw.toLocaleLowerCase('zh-CN').includes(query))
    .slice()
    .reverse();
  const nextIndex = snapshot.items.length ? snapshot.items[snapshot.items.length - 1].index : null;
  elements.resultCount.textContent = `${items.length} 条`;
  if (!items.length) {
    elements.messageList.replaceChildren(emptyState(
      query ? '没有匹配事件' : '当前没有待处理事件',
      query ? '换一个关键词再试' : 'Agent 可能已经快速消费完队列',
    ));
    return;
  }
  syncList(
    elements.messageList,
    items,
    (item) => item.raw,
    (item) => createEventItem(item, `#${item.index}`, 'pending', item.index === nextIndex),
    (node, item) => updateEventItem(node, item, `#${item.index}`, 'pending', item.index === nextIndex),
  );
}

function renderStatus() {
  const status = state.status;
  const statusName = status.state === 'processing' ? '执行中' : status.state === 'idle' ? '等待中' : '未知';
  elements.agentState.textContent = statusName;
  elements.currentTask.className = `current-task ${status.state}`;

  if (status.state === 'processing' && status.event) {
    const startedAt = parseDate(status.started_at);
    const elapsed = startedAt ? Math.max(0, Date.now() - startedAt.getTime()) : null;
    const stuck = elapsed !== null && elapsed > STUCK_PROCESSING_MS;
    const type = eventType({ data: status.event, valid_json: true });
    elements.currentTask.className = `current-task processing${stuck ? ' stuck' : ''}`;
    elements.agentStateDetail.textContent = `${type} · ${elapsed === null ? '时长未知' : formatDuration(elapsed)}${stuck ? ' · 疑似卡死' : ''}`;
    elements.currentTaskTitle.textContent = stuck ? `疑似卡死:${type}` : `正在执行 ${type}`;
    elements.currentTaskDuration.textContent = elapsed === null ? '--' : formatDuration(elapsed);
    elements.currentTaskPreview.textContent = previewText({ data: status.event, valid_json: true, raw: JSON.stringify(status.event) });
    elements.currentTaskRaw.textContent = JSON.stringify(status.event, null, 2);
    elements.currentTaskDetails.hidden = false;
    return;
  }

  if (status.state === 'idle') {
    const updatedAt = parseDate(status.updated_at);
    // Worker 每次循环都会重写 idle 状态(BRPOP 超时约 5 秒),长时间未更新说明 Agent 可能已退出。
    if (!updatedAt || Date.now() - updatedAt.getTime() > STALE_IDLE_MS) {
      elements.agentState.textContent = '疑似离线';
      elements.currentTask.className = 'current-task idle stale';
      elements.agentStateDetail.textContent = updatedAt ? `状态停滞于 ${formatTime(status.updated_at)}` : '状态时间无效';
      elements.currentTaskTitle.textContent = 'Agent 状态更新停滞';
      elements.currentTaskDuration.textContent = 'STALE';
      elements.currentTaskPreview.textContent = '状态 Key 超过 15 秒未更新,Agent 可能已崩溃或被停止,请检查 agent 容器日志。';
      elements.currentTaskDetails.hidden = true;
      return;
    }
    elements.agentStateDetail.textContent = status.updated_at ? `更新于 ${formatTime(status.updated_at)}` : '正在等待 Redis 事件';
    elements.currentTaskTitle.textContent = 'Agent 正在等待任务';
    elements.currentTaskDuration.textContent = 'IDLE';
    elements.currentTaskPreview.textContent = 'Worker 当前阻塞在 Redis BRPOP，队列中没有已弹出且尚未完成的事件。';
    elements.currentTaskDetails.hidden = true;
    return;
  }

  elements.agentStateDetail.textContent = 'Agent 尚未写入状态 Key';
  elements.currentTaskTitle.textContent = '尚未上报状态';
  elements.currentTaskDuration.textContent = '--';
  elements.currentTaskPreview.textContent = '请重启 Agent 服务，使更新后的 task_worker.py 进入主循环并写入状态。';
  elements.currentTaskDetails.hidden = true;
}

function renderHistory() {
  const query = elements.historySearchInput.value.trim().toLocaleLowerCase('zh-CN');
  const items = state.history.filter((item) => !query || JSON.stringify(item).toLocaleLowerCase('zh-CN').includes(query));
  elements.historyResultCount.textContent = `${items.length} 条`;
  if (!items.length) {
    elements.historyList.replaceChildren(emptyState(
      query ? '没有匹配历史' : '暂无已消费历史',
      query ? '换一个关键词再试' : 'Agent 开始处理事件后会写入 MongoDB',
    ));
    return;
  }
  const runningSource = (item) => item === state.history[0] && state.status?.state === 'processing' ? 'running' : 'history';
  syncList(
    elements.historyList,
    items,
    (item) => String(item.created_at),
    (item) => createEventItem(
      { data: item, raw: JSON.stringify(item), valid_json: true },
      formatDateTime(item.created_at),
      runningSource(item),
    ),
    (node, item) => updateEventItem(
      node,
      { data: item, raw: JSON.stringify(item), valid_json: true },
      formatDateTime(item.created_at),
      runningSource(item),
    ),
  );
}

function renderBreakdown(items) {
  const counts = new Map();
  for (const item of items) {
    const type = item && typeof item === 'object' ? String(item.event_type || '未分类') : '非 JSON';
    counts.set(type, (counts.get(type) || 0) + 1);
  }
  const sorted = [...counts.entries()].sort((left, right) => right[1] - left[1]);
  if (!sorted.length) {
    elements.eventBreakdown.innerHTML = '<p class="empty-small">暂无历史数据</p>';
    return;
  }
  elements.eventBreakdown.replaceChildren(...sorted.map(([type, count]) => {
    const row = document.createElement('div');
    row.className = 'event-row';
    row.append(document.createElement('i'));
    const label = document.createElement('span');
    label.textContent = type;
    const value = document.createElement('strong');
    value.textContent = count;
    row.append(label, value);
    return row;
  }));
}

function createEventItem(item, leadingText, source, isNext) {
  const article = document.createElement('article');
  // fresh 仅在新条目创建时存在:只有它播放 reveal 动画,复用的节点不会闪烁。
  article.className = 'message-item fresh';
  const index = document.createElement('span');
  index.className = 'message-index';

  const body = document.createElement('div');
  body.className = 'message-body';
  const title = document.createElement('div');
  title.className = 'message-title';
  const tag = document.createElement('span');
  tag.className = 'event-tag';
  const validity = document.createElement('span');
  validity.className = 'validity';
  title.append(tag, validity);
  const preview = document.createElement('p');
  preview.className = 'message-preview';
  body.append(title, preview);

  const details = document.createElement('details');
  const summary = document.createElement('summary');
  summary.textContent = '查看完整事件';
  const content = document.createElement('pre');
  details.append(summary, content);
  article.append(index, body, details);
  updateEventItem(article, item, leadingText, source, isNext);
  return article;
}

// 仅更新动态部分,供增量同步复用节点时原地刷新,保留 <details> 的展开状态。
function updateEventItem(node, item, leadingText, source, isNext) {
  node.classList.toggle('history-item', source === 'history' || source === 'running');
  node.classList.toggle('running', source === 'running');
  node.classList.toggle('next-consume', Boolean(isNext));
  node.querySelector('.message-index').textContent = leadingText;
  node.querySelector('.event-tag').textContent = eventType(item);
  node.querySelector('.validity').textContent = source === 'running' ? '当前执行' : source === 'history' ? '已开始处理' : isNext ? '下一个消费' : item.valid_json ? '待处理 · JSON' : '待处理 · RAW';
  node.querySelector('.message-preview').textContent = previewText(item);
  node.querySelector('pre').textContent = item.valid_json ? JSON.stringify(item.data, null, 2) : item.raw;
}

function eventType(item) {
  return item.data && typeof item.data === 'object' && !Array.isArray(item.data)
    ? String(item.data.event_type || '未分类')
    : '非 JSON';
}

function previewText(item) {
  if (!item.valid_json) return item.raw.slice(0, 260);
  const payload = item.data && typeof item.data === 'object' ? item.data.payload : null;
  const text = payload?.raw_message || payload?.result || payload?.message;
  return typeof text === 'string' && text ? text.slice(0, 260) : JSON.stringify(item.data).slice(0, 260);
}

// 队列只会从两端进出(LPUSH/RPUSH/BRPOP),长度 + 首尾内容足以识别变化。
function queueSignature(snapshot) {
  const items = snapshot.items || [];
  const first = items.length ? items[0].raw : '';
  const last = items.length ? items[items.length - 1].raw : '';
  return [snapshot.queue, snapshot.length, items.length, first.length, last.length, first.slice(0, 128), last.slice(0, 128)].join('|');
}

// 历史是只增的,新记录插在最前,数量 + 首尾时间戳足以识别变化。
function historySignature(items) {
  const first = items.length ? items[0].created_at : '';
  const last = items.length ? items[items.length - 1].created_at : '';
  return `${items.length}|${first}|${last}`;
}

function emptyState(title, detail) {
  const empty = document.createElement('div');
  empty.className = 'empty-state';
  const strong = document.createElement('strong');
  strong.textContent = title;
  const span = document.createElement('span');
  span.textContent = detail;
  empty.append(strong, span);
  return empty;
}

function showError(element, message) {
  element.textContent = message;
  element.hidden = false;
}

function parseDate(value) {
  if (!value) return null;
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

function formatTime(value) {
  const parsed = parseDate(value);
  return parsed ? parsed.toLocaleTimeString('zh-CN', { hour12: false }) : '--';
}

function formatDateTime(value) {
  const parsed = parseDate(value);
  return parsed ? parsed.toLocaleString('zh-CN', { hour12: false }) : '时间未知';
}

function formatDuration(milliseconds) {
  const seconds = Math.floor(milliseconds / 1000);
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  return `${minutes}m ${seconds % 60}s`;
}

function setConnection(online) {
  elements.connection.className = `connection ${online ? 'online' : 'offline'}`;
  elements.connection.querySelector('strong').textContent = online ? 'Redis 已连接' : 'Redis 不可用';
}

function schedule() {
  window.clearTimeout(state.timer);
  if (!state.paused) state.timer = window.setTimeout(refresh, Number(elements.interval.value));
}

elements.refreshButton.addEventListener('click', refresh);
elements.searchInput.addEventListener('input', () => state.queue && renderQueue());
elements.historySearchInput.addEventListener('input', renderHistory);
elements.interval.addEventListener('change', schedule);
elements.pauseButton.addEventListener('click', () => {
  state.paused = !state.paused;
  elements.pauseButton.classList.toggle('active', state.paused);
  elements.pauseButton.textContent = state.paused ? '▶' : 'Ⅱ';
  elements.pauseButton.title = state.paused ? '继续自动刷新' : '暂停自动刷新';
  elements.pauseButton.setAttribute('aria-label', elements.pauseButton.title);
  elements.refreshState.textContent = state.paused ? '自动刷新已暂停' : '自动刷新已开启';
  schedule();
});

refresh();
