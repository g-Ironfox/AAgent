import { fetchSettings, submitSystemPrompt } from './api.js';

const APPLY_TIMEOUT_MS = 30000;
const POLL_INTERVAL_MS = 500;
const state = { loading: false, saving: false, initialized: false, appliedPrompt: '' };
const elements = {
  form: document.querySelector('#settingForm'),
  input: document.querySelector('#systemPrompt'),
  saveButton: document.querySelector('#saveButton'),
  reloadButton: document.querySelector('#reloadButton'),
  saveStatus: document.querySelector('#saveStatus'),
  settingState: document.querySelector('#settingState'),
  characterCount: document.querySelector('#characterCount'),
};

function setStatus(message, type = '') {
  elements.saveStatus.className = `save-status ${type}`.trim();
  elements.saveStatus.textContent = message;
}

function updateControls() {
  const busy = state.loading || state.saving;
  const changed = elements.input.value !== state.appliedPrompt;
  elements.input.disabled = busy || !state.initialized;
  elements.reloadButton.disabled = busy;
  elements.saveButton.disabled = busy || !state.initialized || !changed || !elements.input.value.trim();
  elements.characterCount.textContent = `${[...elements.input.value].length} / 100000`;
}

async function loadSettings({ preserveInput = false } = {}) {
  if (state.loading || state.saving) return;
  state.loading = true;
  elements.settingState.textContent = '读取中';
  setStatus('');
  updateControls();
  try {
    const settings = await fetchSettings();
    state.appliedPrompt = settings.system_prompt;
    state.initialized = true;
    if (!preserveInput) elements.input.value = state.appliedPrompt;
    elements.settingState.textContent = '已同步';
  } catch (error) {
    elements.settingState.textContent = '不可用';
    setStatus(error.name === 'AbortError' ? '读取超时，请重试' : error.message, 'error');
  } finally {
    state.loading = false;
    updateControls();
  }
}

async function waitUntilApplied(expectedPrompt) {
  const deadline = Date.now() + APPLY_TIMEOUT_MS;
  while (Date.now() < deadline) {
    const settings = await fetchSettings();
    if (settings.system_prompt === expectedPrompt) return;
    await new Promise((resolve) => window.setTimeout(resolve, POLL_INTERVAL_MS));
  }
  throw new Error('等待 Agent 应用设置超时，请重新读取确认');
}

async function saveSettings() {
  const systemPrompt = elements.input.value;
  if (!systemPrompt.trim() || state.saving) return;
  state.saving = true;
  elements.settingState.textContent = '等待应用';
  setStatus('正在优先入队…');
  updateControls();
  try {
    await submitSystemPrompt(systemPrompt);
    setStatus('事件已入队，等待 Agent 确认…');
    await waitUntilApplied(systemPrompt);
    state.appliedPrompt = systemPrompt;
    elements.settingState.textContent = '已同步';
    setStatus('Agent 已应用并同步缓存', 'success');
  } catch (error) {
    elements.settingState.textContent = '待确认';
    setStatus(error.name === 'AbortError' ? '请求超时，请重新读取确认' : error.message, 'error');
  } finally {
    state.saving = false;
    updateControls();
  }
}

elements.form.addEventListener('submit', (event) => {
  event.preventDefault();
  saveSettings();
});
elements.reloadButton.addEventListener('click', () => loadSettings());
elements.input.addEventListener('input', () => {
  if (elements.saveStatus.classList.contains('error')) setStatus('');
  updateControls();
});

loadSettings();