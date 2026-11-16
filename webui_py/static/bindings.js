import {
  createEventBinding,
  deleteEventBinding,
  fetchEventBindings,
  fetchEventBindingWorkflowOptions,
  updateEventBinding,
} from './api.js';

const list = document.querySelector('#bindingList');
const count = document.querySelector('#bindingCount');
const form = document.querySelector('#bindingForm');
const formTitle = document.querySelector('#formTitle');
const formState = document.querySelector('#formState');
const formStatus = document.querySelector('#formStatus');
const emptyState = document.querySelector('#bindingEmpty');
const eventType = document.querySelector('#eventType');
const workflowFile = document.querySelector('#workflowFile');
const contractWorkflowName = document.querySelector('#contractWorkflowName');
const contractInputPorts = document.querySelector('#contractInputPorts');
const contractOutputPorts = document.querySelector('#contractOutputPorts');
const contractInputCount = document.querySelector('#contractInputCount');
const contractOutputCount = document.querySelector('#contractOutputCount');
const enabled = document.querySelector('#enabled');
const saveButton = document.querySelector('#saveBinding');
const cancelButton = document.querySelector('#cancelEdit');
const newButton = document.querySelector('#newBinding');

let bindings = [];
let workflows = [];
let editingId = null;

function setStatus(message, kind = '') {
  formStatus.textContent = message;
  formStatus.className = `form-status ${kind}`;
}

function renderContractPorts(container, ports, emptyMessage) {
  container.replaceChildren();
  if (!ports.length) {
    const empty = document.createElement('p');
    empty.className = 'contract-port-empty';
    empty.textContent = emptyMessage;
    container.append(empty);
    return;
  }
  for (const port of ports) {
    const row = document.createElement('div');
    row.className = 'contract-port-row';
    const name = document.createElement('strong');
    name.textContent = port.name || '未命名字段';
    const type = document.createElement('code');
    type.textContent = port.type || 'content';
    row.append(name, type);
    container.append(row);
  }
}

function renderContractPreview() {
  const workflow = workflows.find((item) => item.file_id === workflowFile.value);
  const inputPorts = workflow?.input_ports || [];
  const outputPorts = workflow?.output_ports || [];
  contractWorkflowName.textContent = workflow ? workflow.name : '未选择 Workflow';
  contractInputCount.textContent = `${inputPorts.length} 个端口`;
  contractOutputCount.textContent = `${outputPorts.length} 个端口`;
  const emptyMessage = workflow ? '暂无字段' : '选择 Workflow 后预览';
  renderContractPorts(contractInputPorts, inputPorts, emptyMessage);
  renderContractPorts(contractOutputPorts, outputPorts, emptyMessage);
}

function resetForm() {
  editingId = null;
  renderList();
  form.classList.remove('open');
  emptyState.hidden = false;
  workflowFile.querySelector('option[data-unavailable]')?.remove();
  form.reset();
  enabled.checked = true;
  formTitle.textContent = '新建事件绑定';
  formState.textContent = '未保存';
  cancelButton.disabled = true;
  setStatus('');
  renderContractPreview();
}

function renderList() {
  list.replaceChildren();
  count.textContent = `${bindings.length} 条`;
  if (!bindings.length) {
    const empty = document.createElement('p');
    empty.className = 'empty-state';
    empty.textContent = '还没有事件绑定。';
    list.append(empty);
    return;
  }
  for (const binding of bindings) {
    const item = document.createElement('article');
    item.className = `binding-item${binding.id === editingId ? ' selected' : ''}`;

    const main = document.createElement('button');
    main.className = 'binding-select';
    main.type = 'button';
    main.addEventListener('click', () => editBinding(binding));

    const event = document.createElement('strong');
    event.textContent = binding.event_type;
    const target = document.createElement('span');
    target.className = 'binding-target';
    const arrow = document.createElement('span');
    arrow.className = 'binding-arrow';
    arrow.textContent = '→';
    const workflow = document.createElement('span');
    workflow.className = 'binding-workflow';
    workflow.textContent = workflows.find((item) => item.file_id === binding.workflow_file_id)?.name
      || binding.workflow_file_name || binding.workflow_name || '文件不可用';
    target.append(arrow, workflow);
    main.append(event, target);

    const meta = document.createElement('div');
    meta.className = 'binding-meta';
    const state = document.createElement('span');
    state.className = binding.enabled ? 'status-enabled' : 'status-disabled';
    state.textContent = binding.enabled ? '已启用' : '已停用';
    const remove = document.createElement('button');
    remove.className = 'delete-button';
    remove.type = 'button';
    remove.textContent = '删除';
    remove.addEventListener('click', () => removeBinding(binding));
    meta.append(state, remove);

    item.append(main, meta);
    list.append(item);
  }
}

function renderWorkflows(items) {
  workflows = items;
  workflowFile.replaceChildren();
  const placeholder = document.createElement('option');
  placeholder.value = '';
  placeholder.textContent = items.length ? '选择 Workspace 中的 Workflow 文件' : '暂无 Workflow 文件，请先在工作区保存 JSON';
  workflowFile.append(placeholder);
  for (const workflow of items) {
    const option = document.createElement('option');
    option.value = workflow.file_id;
    option.textContent = workflow.name;
    workflowFile.append(option);
  }
  workflowFile.disabled = items.length === 0;
  saveButton.disabled = items.length === 0;
  renderContractPreview();
}

function editBinding(binding) {
  editingId = binding.id;
  form.classList.add('open');
  emptyState.hidden = true;
  eventType.value = binding.event_type;
  workflowFile.querySelector('option[data-unavailable]')?.remove();
  if (binding.workflow_file_id && !workflows.some((item) => item.file_id === binding.workflow_file_id)) {
    const unavailable = document.createElement('option');
    unavailable.value = binding.workflow_file_id;
    unavailable.textContent = `${binding.workflow_file_name || binding.workflow_file_id}（文件不可用，请重新选择）`;
    unavailable.disabled = true;
    unavailable.dataset.unavailable = 'true';
    workflowFile.append(unavailable);
  }
  workflowFile.value = binding.workflow_file_id || '';
  renderContractPreview();
  enabled.checked = binding.enabled;
  formTitle.textContent = '编辑事件绑定';
  formState.textContent = '编辑中';
  cancelButton.disabled = false;
  setStatus(binding.workflow_file_id
    ? (workflows.some((item) => item.file_id === binding.workflow_file_id) ? '' : '文件已删除或内容不是有效 Workflow，请重新选择')
    : '旧绑定：请重新选择 Workspace 中的 Workflow 文件', 'error');
  renderList();
}

async function removeBinding(binding) {
  if (!window.confirm(`删除 ${binding.event_type} 的事件绑定？`)) return;
  setStatus('删除中');
  try {
    await deleteEventBinding(binding.id);
    bindings = bindings.filter((item) => item.id !== binding.id);
    if (editingId === binding.id) resetForm();
    renderList();
    setStatus('已删除', 'success');
  } catch (error) {
    setStatus(error.message || '删除失败', 'error');
  }
}

async function load() {
  try {
    const [bindingResponse, workflowResponse] = await Promise.all([
      fetchEventBindings(),
      fetchEventBindingWorkflowOptions(),
    ]);
    bindings = bindingResponse.items || [];
    renderWorkflows(workflowResponse.items || []);
    renderList();
    resetForm();
  } catch (error) {
    count.textContent = '不可用';
    list.textContent = error.message || '事件绑定读取失败';
    setStatus(error.message || '读取失败', 'error');
  }
}

newButton.addEventListener('click', () => {
  resetForm();
  form.classList.add('open');
  emptyState.hidden = true;
  eventType.focus();
});
cancelButton.addEventListener('click', resetForm);
workflowFile.addEventListener('change', () => {
  setStatus('');
  renderContractPreview();
});

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  const payload = {
    event_type: eventType.value.trim().toLowerCase(),
    workflow_file_id: workflowFile.value,
    enabled: enabled.checked,
  };
  saveButton.disabled = true;
  setStatus('保存中');
  try {
    const saved = editingId
      ? await updateEventBinding(editingId, payload)
      : await createEventBinding(payload);
    if (editingId) {
      bindings = bindings.map((item) => (item.id === saved.id ? saved : item));
    } else {
      bindings = [...bindings, saved].sort((left, right) => left.event_type.localeCompare(right.event_type));
    }
    renderList();
    editBinding(saved);
    setStatus('已保存', 'success');
  } catch (error) {
    setStatus(error.message || '保存失败', 'error');
  } finally {
    saveButton.disabled = false;
  }
});

load();
