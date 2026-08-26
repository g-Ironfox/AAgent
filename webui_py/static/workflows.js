import { createWorkflow, deleteWorkflow, fetchWorkflows, renameWorkflow, updateWorkflowMetadata } from './api.js';

const state = { workflows: [], selectedId: null, loading: false, saving: false };
const elements = {
  state: document.querySelector('#workflowState'),
  list: document.querySelector('#workflowList'),
  refreshButton: document.querySelector('#refreshButton'),
  createButton: document.querySelector('#createButton'),
  renameButton: document.querySelector('#renameButton'),
  deleteButton: document.querySelector('#deleteButton'),
  title: document.querySelector('#configurationTitle'),
  editLink: document.querySelector('#editWorkflowLink'),
  empty: document.querySelector('#workflowEmpty'),
  metadataForm: document.querySelector('#metadataForm'),
  metadataStatus: document.querySelector('#metadataStatus'),
  metadataSubmit: document.querySelector('#metadataSubmit'),
  inputPorts: document.querySelector('#inputPorts'),
  outputPorts: document.querySelector('#outputPorts'),
  addInputPort: document.querySelector('#addInputPort'),
  addOutputPort: document.querySelector('#addOutputPort'),
  workflowNodeOptions: document.querySelector('#workflowNodeOptions'),
  portTemplate: document.querySelector('#metadataPortTemplate'),
  createDialog: document.querySelector('#createDialog'),
  createForm: document.querySelector('#createForm'),
  createName: document.querySelector('#createName'),
  createError: document.querySelector('#createError'),
  createSubmit: document.querySelector('#createSubmit'),
  renameDialog: document.querySelector('#renameDialog'),
  renameForm: document.querySelector('#renameForm'),
  renameName: document.querySelector('#renameName'),
  renameError: document.querySelector('#renameError'),
  renameSubmit: document.querySelector('#renameSubmit'),
};

function selectedWorkflow() {
  return state.workflows.find((workflow) => workflow.id === state.selectedId) || null;
}

function workflowSummary(workflow) {
  return {
    ...workflow,
    node_count: workflow.node_count ?? workflow.nodes?.length ?? 0,
    connection_count: workflow.connection_count ?? workflow.connections?.length ?? 0,
  };
}

function updateControls() {
  const selected = Boolean(selectedWorkflow());
  const busy = state.loading || state.saving;
  elements.refreshButton.disabled = busy;
  elements.createButton.disabled = busy;
  elements.renameButton.disabled = busy || !selected;
  elements.deleteButton.disabled = busy || !selected;
  elements.metadataSubmit.disabled = busy || !selected;
  elements.addInputPort.disabled = busy || !selected;
  elements.addOutputPort.disabled = busy || !selected;
}

function createPortRow(port = {}) {
  const row = elements.portTemplate.content.firstElementChild.cloneNode(true);
  row.querySelector('[data-port-name]').value = port.name || '';
  row.querySelector('[data-port-type]').value = port.type || 'content';
  row.querySelector('[data-remove-port]').addEventListener('click', () => row.remove());
  return row;
}

function renderPortList(container, ports) {
  container.replaceChildren(...ports.map((port) => createPortRow(port)));
  if (!ports.length) {
    const empty = document.createElement('p');
    empty.className = 'metadata-port-empty';
    empty.textContent = '暂无字段';
    container.append(empty);
  }
}

function appendPort(container) {
  container.querySelector('.metadata-port-empty')?.remove();
  const row = createPortRow();
  container.append(row);
  row.querySelector('[data-port-name]').focus();
}

function readPortList(container) {
  return Array.from(container.querySelectorAll('.metadata-port-row'), (row) => ({
    name: row.querySelector('[data-port-name]').value.trim(),
    type: row.querySelector('[data-port-type]').value,
  }));
}

function renderWorkflowNodeOptions(workflow) {
  const selectedIds = new Set((workflow.workflow_nodes || []).map((reference) => reference.workflow_id));
  const candidates = state.workflows.filter((candidate) => candidate.id !== workflow.id);
  if (!candidates.length) {
    const empty = document.createElement('p');
    empty.className = 'metadata-port-empty';
    empty.textContent = '没有可引入的其他 Workflow';
    elements.workflowNodeOptions.replaceChildren(empty);
    return;
  }
  elements.workflowNodeOptions.replaceChildren(...candidates.map((candidate) => {
    const label = document.createElement('label');
    label.className = 'metadata-workflow-option';
    const checkbox = document.createElement('input');
    checkbox.type = 'checkbox';
    checkbox.value = candidate.id;
    checkbox.checked = selectedIds.has(candidate.id);
    const description = document.createElement('span');
    const name = document.createElement('strong');
    name.textContent = candidate.name || candidate.id;
    const contract = document.createElement('small');
    contract.textContent = `${(candidate.input_ports || []).length} 输入 / ${(candidate.output_ports || []).length} 输出`;
    description.append(name, contract);
    label.append(checkbox, description);
    return label;
  }));
}

function readWorkflowNodes() {
  return Array.from(elements.workflowNodeOptions.querySelectorAll('input:checked'), (input) => ({ workflow_id: input.value }));
}

function renderConfiguration() {
  const workflow = selectedWorkflow();
  elements.empty.hidden = Boolean(workflow);
  elements.metadataForm.hidden = !workflow;
  elements.editLink.hidden = !workflow;
  elements.renameButton.hidden = !workflow;
  elements.deleteButton.hidden = !workflow;
  elements.title.textContent = workflow?.name || '选择一个 Workflow';
  if (!workflow) {
    elements.editLink.href = '/workflow_edit.html';
    elements.inputPorts.replaceChildren();
    elements.outputPorts.replaceChildren();
    elements.workflowNodeOptions.replaceChildren();
    return;
  }
  elements.editLink.href = `/workflow_edit.html?id=${encodeURIComponent(workflow.id)}`;
  elements.metadataStatus.textContent = '';
  renderPortList(elements.inputPorts, workflow.input_ports || []);
  renderPortList(elements.outputPorts, workflow.output_ports || []);
  renderWorkflowNodeOptions(workflow);
}

function selectWorkflow(id) {
  state.selectedId = id;
  renderList();
  renderConfiguration();
}

function renderList() {
  elements.list.replaceChildren();
  if (!state.workflows.length) {
    const empty = document.createElement('p');
    empty.className = 'workflow-list-empty';
    empty.textContent = state.loading ? '正在读取...' : '还没有 Workflow';
    elements.list.append(empty);
    return;
  }
  for (const workflow of state.workflows) {
    const button = document.createElement('button');
    button.className = `workflow-management-item${workflow.id === state.selectedId ? ' active' : ''}`;
    button.type = 'button';

    const title = document.createElement('strong');
    title.textContent = workflow.name || workflow.id;
    const id = document.createElement('code');
    id.textContent = workflow.id;
    const meta = document.createElement('small');
    meta.textContent = `${workflow.node_count} 节点 / ${workflow.connection_count} 连接`;

    button.append(title, id, meta);
    button.addEventListener('click', () => selectWorkflow(workflow.id));
    elements.list.append(button);
  }
}

async function loadWorkflows() {
  if (state.loading) return;
  state.loading = true;
  elements.state.textContent = '读取中';
  updateControls();
  renderList();
  try {
    const response = await fetchWorkflows();
    state.workflows = response.items;
    if (!state.workflows.some((workflow) => workflow.id === state.selectedId)) {
      state.selectedId = state.workflows[0]?.id || null;
    }
    elements.state.textContent = `共 ${state.workflows.length} 个`;
  } catch (error) {
    state.workflows = [];
    state.selectedId = null;
    elements.state.textContent = error.name === 'AbortError' ? '读取超时' : '不可用';
  } finally {
    state.loading = false;
    updateControls();
    renderList();
    renderConfiguration();
  }
}

function openCreateDialog() {
  elements.createForm.reset();
  elements.createError.textContent = '';
  elements.createDialog.showModal();
  elements.createName.focus();
}

function openRenameDialog() {
  const workflow = selectedWorkflow();
  if (!workflow) return;
  elements.renameName.value = workflow.name;
  elements.renameError.textContent = '';
  elements.renameDialog.showModal();
  elements.renameName.focus();
  elements.renameName.select();
}

async function submitCreate(event) {
  event.preventDefault();
  if (state.saving || !elements.createForm.reportValidity()) return;
  state.saving = true;
  elements.createSubmit.disabled = true;
  elements.createError.textContent = '';
  updateControls();
  try {
    const created = workflowSummary(await createWorkflow(elements.createName.value.trim()));
    state.workflows.unshift(created);
    state.selectedId = created.id;
    elements.createDialog.close();
    elements.state.textContent = `共 ${state.workflows.length} 个`;
    renderList();
    renderConfiguration();
  } catch (error) {
    elements.createError.textContent = error.name === 'AbortError' ? '创建超时，请重试' : error.message;
  } finally {
    state.saving = false;
    elements.createSubmit.disabled = false;
    updateControls();
  }
}

async function submitRename(event) {
  event.preventDefault();
  const workflow = selectedWorkflow();
  if (!workflow || state.saving || !elements.renameForm.reportValidity()) return;
  state.saving = true;
  elements.renameSubmit.disabled = true;
  elements.renameError.textContent = '';
  updateControls();
  try {
    const renamed = workflowSummary(await renameWorkflow(workflow.id, elements.renameName.value.trim()));
    const index = state.workflows.findIndex((item) => item.id === workflow.id);
    state.workflows[index] = renamed;
    elements.renameDialog.close();
    renderList();
    renderConfiguration();
  } catch (error) {
    elements.renameError.textContent = error.name === 'AbortError' ? '重命名超时，请重试' : error.message;
  } finally {
    state.saving = false;
    elements.renameSubmit.disabled = false;
    updateControls();
  }
}

async function removeSelectedWorkflow() {
  const workflow = selectedWorkflow();
  if (!workflow || state.saving || !window.confirm(`确定删除“${workflow.name}”吗？此操作无法撤销。`)) return;
  state.saving = true;
  updateControls();
  try {
    await deleteWorkflow(workflow.id);
    state.workflows = state.workflows.filter((item) => item.id !== workflow.id);
    state.selectedId = state.workflows[0]?.id || null;
    elements.state.textContent = `共 ${state.workflows.length} 个`;
    renderList();
    renderConfiguration();
  } catch (error) {
    elements.state.textContent = error.name === 'AbortError' ? '删除超时' : (error.message || '删除失败');
  } finally {
    state.saving = false;
    updateControls();
  }
}

async function submitMetadata(event) {
  event.preventDefault();
  const workflow = selectedWorkflow();
  if (!workflow || state.saving || !elements.metadataForm.reportValidity()) return;
  const inputPorts = readPortList(elements.inputPorts);
  const outputPorts = readPortList(elements.outputPorts);
  const workflowNodes = readWorkflowNodes();
  const hasDuplicateNames = (ports) => {
    const names = ports.map((port) => port.name.trim().toLocaleLowerCase());
    return new Set(names).size !== names.length;
  };
  if (hasDuplicateNames(inputPorts)) {
    elements.metadataStatus.textContent = '输入 Port 名称不能重名';
    return;
  }
  if (hasDuplicateNames(outputPorts)) {
    elements.metadataStatus.textContent = '输出 Port 名称不能重名';
    return;
  }
  state.saving = true;
  elements.metadataStatus.textContent = '保存中';
  updateControls();
  try {
    const updated = workflowSummary(await updateWorkflowMetadata(workflow.id, inputPorts, outputPorts, workflowNodes));
    const index = state.workflows.findIndex((item) => item.id === workflow.id);
    state.workflows[index] = updated;
    elements.metadataStatus.textContent = '已保存';
  } catch (error) {
    elements.metadataStatus.textContent = error.name === 'AbortError' ? '保存超时' : error.message;
  } finally {
    state.saving = false;
    updateControls();
  }
}

elements.refreshButton.addEventListener('click', loadWorkflows);
elements.createButton.addEventListener('click', openCreateDialog);
elements.renameButton.addEventListener('click', openRenameDialog);
elements.deleteButton.addEventListener('click', removeSelectedWorkflow);
elements.addInputPort.addEventListener('click', () => appendPort(elements.inputPorts));
elements.addOutputPort.addEventListener('click', () => appendPort(elements.outputPorts));
elements.metadataForm.addEventListener('submit', submitMetadata);
elements.createForm.addEventListener('submit', submitCreate);
elements.renameForm.addEventListener('submit', submitRename);
for (const button of document.querySelectorAll('[data-close-dialog]')) {
  button.addEventListener('click', () => button.closest('dialog').close());
}
loadWorkflows();