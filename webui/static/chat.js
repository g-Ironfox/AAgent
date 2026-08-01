import { submitChat } from './api.js';

const state = { sending: false };
const elements = {
  form: document.querySelector('#chatForm'),
  input: document.querySelector('#messageInput'),
  sendButton: document.querySelector('#sendButton'),
  sendStatus: document.querySelector('#sendStatus'),
  characterCount: document.querySelector('#characterCount'),
  messageList: document.querySelector('#messageList'),
  empty: document.querySelector('#chatEmpty'),
  connection: document.querySelector('#chatConnection'),
  queueName: document.querySelector('#queueName'),
};

function resizeInput() {
  elements.input.style.height = 'auto';
  elements.input.style.height = `${Math.min(elements.input.scrollHeight, 180)}px`;
  elements.characterCount.textContent = `${[...elements.input.value].length} / 4000`;
}

function setConnection(online, label) {
  elements.connection.className = `connection ${online ? 'online' : 'offline'}`;
  elements.connection.querySelector('span').textContent = label;
}

function appendMessage(event) {
  elements.empty?.remove();
  const article = document.createElement('article');
  article.className = 'chat-message';

  const meta = document.createElement('div');
  meta.className = 'message-meta';
  const author = document.createElement('strong');
  author.textContent = 'YOU';
  const time = document.createElement('time');
  const sentAt = new Date(event.time);
  time.dateTime = event.time;
  time.textContent = Number.isNaN(sentAt.getTime())
    ? event.time
    : sentAt.toLocaleTimeString('zh-CN', { hour12: false, hour: '2-digit', minute: '2-digit' });
  meta.append(author, time);

  const content = document.createElement('p');
  content.textContent = event.payload.message;
  article.append(meta, content);
  elements.messageList.append(article);
  elements.messageList.scrollTo({ top: elements.messageList.scrollHeight, behavior: 'smooth' });
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
    const result = await submitChat(message);
    appendMessage(result.event);
    elements.queueName.textContent = result.queue;
    elements.input.value = '';
    elements.sendStatus.className = 'send-status success';
    elements.sendStatus.textContent = '已进入队列';
    setConnection(true, '队列可用');
  } catch (error) {
    elements.sendStatus.className = 'send-status error';
    elements.sendStatus.textContent = error.name === 'AbortError' ? '请求超时，请重试' : error.message;
    setConnection(false, '发送失败');
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