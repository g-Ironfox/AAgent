import { fetchTerminalHistory, fetchTerminalSessions, submitTerminal, fetchProcessWorkflowOptions, createProcess } from './api.js';
import { createAutoRefresh } from './auto-refresh.js';

const state = {
  sending: false,
  loading: false,
  historyLoaded: false,
  seen: new Set(),
  terminalProcessId: null,
  terminalClosed: false,
  refreshPending: false,
  drafts: new Map(),
  sessions: [],
  creating: false,
  workflows: [],
  sessionRevision: 0,
};
const elements = {
  createButton: document.querySelector('#createProcessButton'),
  createDialog: document.querySelector('#createProcessDialog'),
  createForm: document.querySelector('#createProcessForm'),
  workflowSelect: document.querySelector('#processWorkflowSelect'),
  processInputs: document.querySelector('#processInputs'),
  createStatus: document.querySelector('#processCreateStatus'),
  submitProcess: document.querySelector('#submitProcessButton'),
  closeDialog: document.querySelector('#closeProcessDialog'),
  cancelDialog: document.querySelector('#cancelProcessDialog'),
  form: document.querySelector('#terminalForm'),
  input: document.querySelector('#messageInput'),
  sendButton: document.querySelector('#sendButton'),
  sendStatus: document.querySelector('#sendStatus'),
  characterCount: document.querySelector('#characterCount'),
  messageList: document.querySelector('#messageList'),
  empty: document.querySelector('#terminalEmpty'),
  latestButton: document.querySelector('#terminalLatestButton'),
  terminalSelect: document.querySelector('#terminalSelect'),
  title: document.querySelector('#terminalTitle'),
  lastRefresh: document.querySelector('#terminalLastRefresh'),
  refreshState: document.querySelector('#terminalRefreshState'),
  interval: document.querySelector('#terminalInterval'),
  pauseButton: document.querySelector('#terminalPauseButton'),
  refreshButton: document.querySelector('#terminalRefreshButton'),
};

async function refreshStatus() {
  if (state.loading) {
    state.refreshPending = true;
    return;
  }
  state.loading = true;
  elements.refreshButton.disabled = true;
  try {
    const revision = state.sessionRevision;
    const sessionResult = await fetchTerminalSessions();
    if (revision !== state.sessionRevision) return;
    const previousTerminalProcessId = state.terminalProcessId;
    updateTerminalOptions(sessionResult.sessions || []);
    if (previousTerminalProcessId !== state.terminalProcessId) resetHistory();
    const terminalProcessId = state.terminalProcessId || '';
    if (!terminalProcessId) {
      resetHistory();
      elements.lastRefresh.textContent = '暂无可用终端会话';
      elements.lastRefresh.classList.remove('sync-error');
      return;
    }
    const snapshot = await fetchTerminalHistory(150, terminalProcessId);
    if (terminalProcessId !== state.terminalProcessId) return;
    appendHistory(snapshot.items);
    elements.lastRefresh.textContent = new Date(snapshot.fetched_at).toLocaleTimeString('zh-CN', { hour12: false });
    elements.lastRefresh.classList.remove('sync-error');
  } catch (error) {
    elements.lastRefresh.classList.add('sync-error');
    elements.lastRefresh.textContent = error.name === 'AbortError' ? '同步超时' : '同步失败';
  } finally {
    state.loading = false;
    elements.refreshButton.disabled = false;
    if (state.refreshPending) {
      state.refreshPending = false;
      refreshStatus();
    } else {
      autoRefresh.schedule();
    }
  }
}

function updateTerminalOptions(sessions) {
  state.sessions = sessions;
  const select = elements.terminalSelect;
  const availableIds = new Set(sessions.map((session) => session.terminal_process_id));
  if (state.terminalProcessId === null) {
    state.terminalProcessId = sessions.find((session) => session.status !== 'terminated')
      ?.terminal_process_id || '';
  } else if (state.terminalProcessId && !availableIds.has(state.terminalProcessId)) {
    state.terminalProcessId = '';
  }

  const options = sessions.length ? [] : [document.createElement('option')];
  if (!sessions.length) {
    options[0].value = '';
    options[0].textContent = '暂无进程终端';
  }
  for (const session of sessions) {
    if (!session.terminal_process_id) continue;
    const option = document.createElement('option');
    option.value = session.terminal_process_id;
    const parent = String(session.parent_process_id || session.terminal_process_id);
    const stateLabel = session.status === 'terminated' ? '已关闭' : '运行中';
    option.textContent = `${parent.slice(0, 12)} · ${stateLabel}`;
    options.push(option);
  }
  select.replaceChildren(...options);
  select.value = state.terminalProcessId;
  elements.title.textContent = state.terminalProcessId
    ? `进程终端 · ${state.terminalProcessId.slice(0, 8)}`
    : '请先创建进程';
  state.terminalClosed = Boolean(
    state.terminalProcessId
    && sessions.find((session) => session.terminal_process_id === state.terminalProcessId)?.status === 'terminated'
  );
  updateComposerState();
}

function updateComposerState() {
  elements.input.disabled = state.sending || state.creating || state.terminalClosed || !state.terminalProcessId;
  elements.sendButton.disabled = state.sending || state.creating || state.terminalClosed || !state.terminalProcessId;
  elements.terminalSelect.disabled = state.sending || state.creating;
  elements.createButton.disabled = state.sending || state.creating;
}

function resetHistory() {
  state.seen.clear();
  state.historyLoaded = false;
  elements.latestButton.classList.remove('has-updates');
  elements.messageList.replaceChildren();
  const empty = document.createElement('div');
  empty.id = 'terminalEmpty';
  empty.className = 'terminal-empty';
  const mark = document.createElement('span');
  mark.className = 'empty-mark';
  mark.setAttribute('aria-hidden', 'true');
  mark.textContent = 'A';
  const title = document.createElement('strong');
  title.textContent = '终端';
  const detail = document.createElement('small');
  detail.textContent = '发送消息开始对话，Agent 的终端输出将在这里追加';
  empty.append(mark, title, detail);
  elements.messageList.append(empty);
  elements.empty = empty;
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
  const isOutput = item.role === 'assistant';
  elements.empty?.remove();
  const article = document.createElement('article');
  article.className = `terminal-message ${isOutput ? 'response-message' : 'command-message'}`;
  article.dataset.id = item.id;

  const meta = document.createElement('div');
  meta.className = 'message-meta';
  const author = document.createElement('strong');
  author.textContent = isOutput ? 'AGENT' : 'TERMINAL';
  const time = document.createElement('time');
  const sentAt = new Date(item.created_at);
  time.dateTime = item.created_at;
  time.textContent = Number.isNaN(sentAt.getTime())
    ? '时间未知'
    : sentAt.toLocaleTimeString('zh-CN', { hour12: false, hour: '2-digit', minute: '2-digit' });
  meta.append(author, time);

  const content = document.createElement('p');
  content.textContent = item.content;
  article.append(meta, content);
  elements.messageList.append(article);
}

async function sendMessage() {
  const content = elements.input.value.trim();
  if (!content || !state.terminalProcessId || state.sending || state.creating || state.terminalClosed) return;

  const targetTerminalProcessId = state.terminalProcessId;
  state.sending = true;
  updateComposerState();
  elements.sendStatus.className = 'send-status';
  elements.sendStatus.textContent = '正在发送…';

  try {
    const result = await submitTerminal(content, targetTerminalProcessId);
    if (targetTerminalProcessId !== state.terminalProcessId) return;
    appendHistory([result.message]);
    elements.input.value = '';
    elements.sendStatus.className = 'send-status success';
    elements.sendStatus.textContent = '消息已保存';
    refreshStatus();
  } catch (error) {
    elements.sendStatus.className = 'send-status error';
    elements.sendStatus.textContent = error.name === 'AbortError' ? '请求超时，请重试' : error.message;
  } finally {
    state.sending = false;
    updateComposerState();
    resizeInput();
    elements.input.focus();
  }
}

async function openCreateProcess() {
  if (state.sending || state.creating) return;
  elements.createStatus.textContent = '';
  elements.createStatus.className = 'send-status';
  elements.submitProcess.disabled = true;
  elements.workflowSelect.disabled = true;
  elements.createDialog.showModal();
  try {
    const result = await fetchProcessWorkflowOptions();
    state.workflows = result.items || [];
    const previous = elements.workflowSelect.value;
    const options = state.workflows.map((workflow) => {
      const option = document.createElement('option');
      option.value = workflow.file_id;
      option.textContent = workflow.name;
      return option;
    });
    elements.workflowSelect.replaceChildren(...options);
    if (state.workflows.some((item) => item.file_id === previous)) {
      elements.workflowSelect.value = previous;
    } else {
      elements.workflowSelect.value = state.workflows[0]?.file_id || '';
      fillProcessInputs();
    }
    if (!options.length) throw new Error('工作区中暂无工作流，请先在工作区创建并保存工作流文件');
    elements.submitProcess.disabled = false;
  } catch (error) {
    elements.createStatus.className = 'send-status error';
    elements.createStatus.textContent = error.message;
  } finally {
    elements.workflowSelect.disabled = false;
  }
}

function fillProcessInputs() {
  const workflow = state.workflows.find((item) => item.file_id === elements.workflowSelect.value);
  const references = {
    content: '',
    message: { role: 'user', content: '' },
    'list-content': [],
    'list-message': [],
    'map-content': {},
  };
  elements.processInputs.value = JSON.stringify(Object.fromEntries(
    (workflow?.input_ports || []).map((port) => [
      port.name, Object.hasOwn(references, port.type) ? references[port.type] : null,
    ])
  ), null, 2);
}

async function submitNewProcess() {
  if (state.creating) return;
  elements.createStatus.textContent = '';
  let inputs;
  try {
    inputs = JSON.parse(elements.processInputs.value.trim() || '{}');
    if (!inputs || typeof inputs !== 'object' || Array.isArray(inputs)) throw new Error();
  } catch {
    elements.createStatus.className = 'send-status error';
    elements.createStatus.textContent = '输入参数必须是合法的 JSON 对象';
    return;
  }
  if (!elements.workflowSelect.value) return;
  state.creating = true;
  elements.submitProcess.disabled = true;
  elements.workflowSelect.disabled = true;
  elements.processInputs.disabled = true;
  elements.closeDialog.disabled = true;
  elements.cancelDialog.disabled = true;
  updateComposerState();
  try {
    const result = await createProcess(elements.workflowSelect.value, inputs);
    state.drafts.set(state.terminalProcessId || '', elements.input.value);
    state.sessionRevision += 1;
    state.terminalProcessId = result.terminal_process_id;
    updateTerminalOptions([{
      terminal_process_id: result.terminal_process_id,
      parent_process_id: result.process_id,
      status: 'waiting_for_input',
      start_time: result.start_time,
    }, ...state.sessions]);
    elements.input.value = '';
    elements.sendStatus.className = 'send-status success';
    elements.sendStatus.textContent = '进程已创建：' + result.process_id;
    resetHistory();
    resizeInput();
    elements.createDialog.close();
    await refreshStatus();
  } catch (error) {
    elements.createStatus.className = 'send-status error';
    elements.createStatus.textContent = error.name === 'AbortError'
      ? '创建请求超时。服务端可能已经创建进程，请先刷新终端会话确认后再重试。'
      : error.message;
  } finally {
    state.creating = false;
    elements.submitProcess.disabled = false;
    elements.workflowSelect.disabled = false;
    elements.processInputs.disabled = false;
    elements.closeDialog.disabled = false;
    elements.cancelDialog.disabled = false;
    updateComposerState();
  }
}

elements.createButton.addEventListener('click', openCreateProcess);
elements.workflowSelect.addEventListener('change', fillProcessInputs);
elements.createForm.addEventListener('submit', (event) => {
  event.preventDefault();
  submitNewProcess();
});
for (const button of [elements.closeDialog, elements.cancelDialog]) {
  button.addEventListener('click', () => { if (!state.creating) elements.createDialog.close(); });
}
elements.createDialog.addEventListener('cancel', (event) => {
  if (state.creating) event.preventDefault();
});

elements.form.addEventListener('submit', (event) => {
  event.preventDefault();
  sendMessage();
});
elements.refreshButton.addEventListener('click', refreshStatus);
elements.terminalSelect.addEventListener('change', () => {
  state.drafts.set(state.terminalProcessId || '', elements.input.value);
  state.terminalProcessId = elements.terminalSelect.value;
  updateTerminalOptions(state.sessions);
  elements.input.value = state.drafts.get(state.terminalProcessId) || '';
  elements.sendStatus.textContent = '';
  resizeInput();
  resetHistory();
  refreshStatus();
});
elements.latestButton.addEventListener('click', () => {
  elements.latestButton.classList.remove('has-updates');
  elements.messageList.scrollTo({ top: elements.messageList.scrollHeight, behavior: 'smooth' });
});
elements.messageList.addEventListener('scroll', () => {
  if (isNearBottom()) elements.latestButton.classList.remove('has-updates');
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

const autoRefresh = createAutoRefresh({
  refresh: refreshStatus,
  interval: elements.interval,
  pauseButton: elements.pauseButton,
  refreshState: elements.refreshState,
  onResume: refreshStatus,
});

resizeInput();
elements.input.focus();
refreshStatus();
