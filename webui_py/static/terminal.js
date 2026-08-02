import { fetchTerminalHistory, submitTerminal } from './api.js';

const state = { sending: false, paused: false, loading: false, historyLoaded: false, timer: null, seen: new Set() };
const elements = {
  form: document.querySelector('#terminalForm'),
  input: document.querySelector('#messageInput'),
  sendButton: document.querySelector('#sendButton'),
  sendStatus: document.querySelector('#sendStatus'),
  characterCount: document.querySelector('#characterCount'),
  messageList: document.querySelector('#messageList'),
  empty: document.querySelector('#terminalEmpty'),
  latestButton: document.querySelector('#terminalLatestButton'),
  queueName: document.querySelector('#queueName'),
  lastRefresh: document.querySelector('#terminalLastRefresh'),
  refreshState: document.querySelector('#terminalRefreshState'),
  interval: document.querySelector('#terminalInterval'),
  pauseButton: document.querySelector('#terminalPauseButton'),
  refreshButton: document.querySelector('#terminalRefreshButton'),
};

async function refreshStatus() {
  if (state.loading) return;
  state.loading = true;
  elements.refreshButton.disabled = true;
  try {
    const snapshot = await fetchTerminalHistory();
    appendHistory(snapshot.items);
    elements.lastRefresh.textContent = new Date(snapshot.fetched_at).toLocaleTimeString('zh-CN', { hour12: false });
    elements.lastRefresh.classList.remove('sync-error');
  } catch (error) {
    elements.lastRefresh.classList.add('sync-error');
    elements.lastRefresh.textContent = error.name === 'AbortError' ? '同步超时' : '同步失败';
  } finally {
    state.loading = false;
    elements.refreshButton.disabled = false;
    scheduleRefresh();
  }
}

function scheduleRefresh() {
  window.clearTimeout(state.timer);
  if (!state.paused) state.timer = window.setTimeout(refreshStatus, Number(elements.interval.value));
}

function resizeInput() {
  elements.input.style.height = 'auto';
  elements.input.style.height = `${Math.min(elements.input.scrollHeight, 180)}px`;
  elements.characterCount.textContent = `${[...elements.input.value].length} / 4000`;
}

function appendHistory(items) {
  const wasNearBottom = isNearBottom();
  let appended = false;
  for (const item of items) {
    if (!item.id || state.seen.has(item.id)) continue;
    state.seen.add(item.id);
    appendMessage(item);
    appended = true;
  }
  if (appended) {
    if (!state.historyLoaded || wasNearBottom) {
      elements.messageList.scrollTo({
        top: elements.messageList.scrollHeight,
        behavior: state.historyLoaded ? 'smooth' : 'auto',
      });
    }
    if (state.historyLoaded && !wasNearBottom) elements.latestButton.classList.add('has-updates');
  }
  state.historyLoaded = true;
}

function isNearBottom() {
  const remaining = elements.messageList.scrollHeight - elements.messageList.scrollTop - elements.messageList.clientHeight;
  return remaining <= 24;
}

function appendMessage(item) {
  const event = item.event || {};
  const type = event.event_type;
  const payload = event.payload || {};
  elements.empty?.remove();
  const article = document.createElement('article');
  article.className = `terminal-message ${type === 'response' ? 'response-message' : 'command-message'}`;
  article.dataset.id = item.id;

  const meta = document.createElement('div');
  meta.className = 'message-meta';
  const author = document.createElement('strong');
  author.textContent = type === 'response' ? 'AGENT' : 'TERMINAL';
  const time = document.createElement('time');
  const sentAt = new Date(item.created_at);
  time.dateTime = item.created_at;
  time.textContent = Number.isNaN(sentAt.getTime())
    ? '时间未知'
    : sentAt.toLocaleTimeString('zh-CN', { hour12: false, hour: '2-digit', minute: '2-digit' });
  meta.append(author, time);

  const content = document.createElement('p');
  content.textContent = type === 'response'
    ? payload.content || (payload.tool_calls?.length ? '[工具调用]' : '[空响应]')
    : payload.message || '[空命令]';
  article.append(meta, content);
  elements.messageList.append(article);
}

async function sendMessage() {
  const message = elements.input.value.trim();
  if (!message || state.sending) return;

  state.sending = true;
  elements.sendButton.disabled = true;
  elements.input.disabled = true;
  elements.sendStatus.className = 'send-status';
  elements.sendStatus.textContent = '正在入队…';

  try {
    const result = await submitTerminal(message);
    elements.queueName.textContent = result.queue;
    elements.input.value = '';
    elements.sendStatus.className = 'send-status success';
    elements.sendStatus.textContent = '已优先入队，等待消费';
    refreshStatus();
  } catch (error) {
    elements.sendStatus.className = 'send-status error';
    elements.sendStatus.textContent = error.name === 'AbortError' ? '请求超时，请重试' : error.message;
  } finally {
    state.sending = false;
    elements.sendButton.disabled = false;
    elements.input.disabled = false;
    resizeInput();
    elements.input.focus();
  }
}

elements.form.addEventListener('submit', (event) => {
  event.preventDefault();
  sendMessage();
});
elements.interval.addEventListener('change', scheduleRefresh);
elements.refreshButton.addEventListener('click', refreshStatus);
elements.latestButton.addEventListener('click', () => {
  elements.latestButton.classList.remove('has-updates');
  elements.messageList.scrollTo({ top: elements.messageList.scrollHeight, behavior: 'smooth' });
});
elements.messageList.addEventListener('scroll', () => {
  if (isNearBottom()) elements.latestButton.classList.remove('has-updates');
});
elements.pauseButton.addEventListener('click', () => {
  state.paused = !state.paused;
  elements.pauseButton.classList.toggle('active', state.paused);
  elements.pauseButton.querySelector('.pause-icon').classList.toggle('play', state.paused);
  elements.pauseButton.title = state.paused ? '继续自动刷新' : '暂停自动刷新';
  elements.pauseButton.setAttribute('aria-label', elements.pauseButton.title);
  elements.refreshState.textContent = state.paused ? '自动刷新已暂停' : '自动刷新已开启';
  if (state.paused) scheduleRefresh();
  else refreshStatus();
});
elements.input.addEventListener('input', () => {
  resizeInput();
  if (elements.sendStatus.classList.contains('error')) elements.sendStatus.textContent = '';
});
elements.input.addEventListener('keydown', (event) => {
  if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {
    event.preventDefault();
    sendMessage();
  }
});

resizeInput();
elements.input.focus();
refreshStatus();