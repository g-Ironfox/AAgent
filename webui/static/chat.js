import { fetchChatHistory, sendChatMessage } from './api.js';

const state = { messages: [], signature: '', waiting: false, forceWaiting: false, loading: false, timer: null };

const elements = {
  list: document.querySelector('#messageList'),
  form: document.querySelector('#chatForm'),
  input: document.querySelector('#chatInput'),
  sendButton: document.querySelector('#sendButton'),
  status: document.querySelector('#chatStatus'),
  count: document.querySelector('#chatCount'),
  connection: document.querySelector('#connection'),
};

const sourceLabel = { web: '网页', qq: 'QQ 私聊', group: 'QQ 群聊' };

function sourceOf(message) {
  if (message.source === 'qq' && message.group_id) return 'group';
  return message.source === 'web' ? 'web' : 'qq';
}

function messageKey(message) {
  return `${message.id}|${message.role}|${message.source}|${message.content}`;
}

async function refresh() {
  if (state.loading) return;
  state.loading = true;
  try {
    const messages = await fetchChatHistory(200);
    state.messages = messages;
    renderMessages();
    updatePendingState();
    setConnection(true);
  } catch (error) {
    setConnection(false);
    elements.status.textContent = `历史接口不可用：${error.message}`;
  } finally {
    state.loading = false;
    schedule();
  }
}

function renderMessages() {
  const signature = state.messages.map(messageKey).join('\u0001');
  if (signature === state.signature) return;
  state.signature = signature;
  const fragment = document.createDocumentFragment();
  for (const message of state.messages) fragment.append(createMessageRow(message));
  elements.list.replaceChildren(fragment);
  elements.count.textContent = `${state.messages.length} 条消息`;
  scrollToBottom();
}

function createMessageRow(message) {
  const row = document.createElement('article');
  row.className = `chat-msg ${message.role === 'user' ? 'user' : 'assistant'}`;

  const meta = document.createElement('div');
  meta.className = 'chat-meta';
  const label = document.createElement('span');
  label.className = 'chat-source';
  label.textContent = sourceLabel[sourceOf(message)] || message.source;
  const time = document.createElement('time');
  const date = new Date(message.created_at);
  time.textContent = Number.isNaN(date.getTime()) ? '' : date.toLocaleTimeString('zh-CN', { hour12: false });
  meta.append(label, time);

  const bubble = document.createElement('div');
  bubble.className = 'chat-bubble';
  const text = document.createElement('p');
  text.textContent = message.content || '(空消息)';
  bubble.append(text);

  row.append(meta, bubble);
  return row;
}

function updatePendingState() {
  const users = state.messages.filter((message) => message.role === 'user' && message.source === 'web');
  const replies = state.messages.filter((message) => message.role === 'assistant');
  const lastUser = users[users.length - 1];
  const lastReply = replies[replies.length - 1];
  const replySeen = Boolean(lastUser && lastReply) && new Date(lastReply.created_at) > new Date(lastUser.created_at);
  const unanswered = Boolean(lastUser) && !replySeen;
  const waiting = state.forceWaiting || unanswered;
  if (!replySeen) state.forceWaiting = false;

  const typing = elements.list.querySelector('.chat-typing');
  if (waiting) {
    if (!typing) {
      const row = document.createElement('article');
      row.className = 'chat-msg assistant chat-typing';
      const bubble = document.createElement('div');
      bubble.className = 'chat-bubble typing';
      bubble.textContent = 'Agent 正在思考…';
      row.append(bubble);
      elements.list.append(row);
      scrollToBottom();
    }
    elements.status.textContent = '等待 Agent 回复…';
  } else {
    if (typing) typing.remove();
    elements.status.textContent = '与 Agent 共享同一上下文(QQ + Web)';
  }
  state.waiting = waiting;
}

function scrollToBottom() {
  elements.list.scrollTop = elements.list.scrollHeight;
}

function setConnection(online) {
  elements.connection.className = `connection ${online ? 'online' : 'offline'}`;
  elements.connection.querySelector('span').textContent = online ? '已同步' : '连接失败';
}

function schedule() {
  window.clearTimeout(state.timer);
  state.timer = window.setTimeout(refresh, 2000);
}

function autoGrow() {
  elements.input.style.height = 'auto';
  elements.input.style.height = `${Math.min(elements.input.scrollHeight, 160)}px`;
}

async function sendMessage() {
  const message = elements.input.value.trim();
  if (!message || state.loading) return;
  elements.input.value = '';
  autoGrow();
  elements.sendButton.disabled = true;
  try {
    await sendChatMessage(message);
    state.forceWaiting = true;
    state.waiting = true;
    elements.status.textContent = '等待 Agent 回复…';
    await refresh();
  } catch (error) {
    elements.status.textContent = `发送失败：${error.message}`;
    elements.input.value = message;
    autoGrow();
  } finally {
    elements.sendButton.disabled = false;
  }
}

elements.form.addEventListener('submit', (event) => {
  event.preventDefault();
  sendMessage();
});
elements.input.addEventListener('keydown', (event) => {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault();
    elements.form.requestSubmit();
  }
});
elements.input.addEventListener('input', autoGrow);

refresh();
