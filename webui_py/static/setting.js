import { fetchSettings, fetchWorkflows, updateSettings } from './api.js';

const form = document.querySelector('#settingsForm');
const options = document.querySelector('#workflowOptions');
const status = document.querySelector('#settingsStatus');
const submit = document.querySelector('#settingsSubmit');

function renderOptions(items, selectedId) {
  options.replaceChildren();
  if (!items.length) {
    const empty = document.createElement('p');
    empty.textContent = '暂无 Workflow，请先创建。';
    options.append(empty);
    return;
  }
  const legend = document.createElement('legend');
  legend.textContent = 'Workflow 列表';
  options.append(legend);
  for (const workflow of items) {
    const label = document.createElement('label');
    label.className = 'workflow-option';
    const input = document.createElement('input');
    input.type = 'radio';
    input.name = 'workflow_id';
    input.value = workflow.id;
    input.checked = workflow.id === selectedId;
    const text = document.createElement('span');
    text.textContent = workflow.name || workflow.id;
    label.append(input, text);
    options.append(label);
  }
}

async function load() {
  try {
    const [workflowResponse, settings] = await Promise.all([fetchWorkflows(), fetchSettings()]);
    renderOptions(workflowResponse.items, settings.workflow_id);
    options.disabled = workflowResponse.items.length === 0;
    submit.disabled = workflowResponse.items.length === 0;
    status.textContent = settings.workflow_id ? '已载入' : '未选择';
  } catch (error) {
    options.replaceChildren();
    const failure = document.createElement('p');
    failure.textContent = error.message || '设置读取失败';
    options.append(failure);
    status.textContent = '不可用';
  }
}

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  const selected = form.querySelector('input[name="workflow_id"]:checked');
  if (!selected) {
    status.textContent = '请选择一个 Workflow';
    return;
  }
  submit.disabled = true;
  status.textContent = '保存中';
  try {
    await updateSettings(selected.value);
    status.textContent = '已保存';
  } catch (error) {
    status.textContent = error.message || '保存失败';
  } finally {
    submit.disabled = false;
  }
});

load();