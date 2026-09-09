import { createWorkflow, deleteWorkflow, fetchWorkflows, renameWorkflow, updateWorkflowMetadata, uploadWorkflow } from './api.js';

const state = { workflows: [], selectedId: null, loading: false, saving: false, pendingUpload: null };
const elements = {
  state: document.querySelector('#workflowState'),
  list: document.querySelector('#workflowList'),
  refreshButton: document.querySelector('#refreshButton'),
  uploadButton: document.querySelector('#uploadButton'),
  uploadFileInput: document.querySelector('#uploadFileInput'),
  uploadDialog: document.querySelector('#uploadDialog'),
  uploadForm: document.querySelector('#uploadForm'),
  uploadName: document.querySelector('#uploadName'),
  uploadError: document.querySelector('#uploadError'),
  uploadSubmit: document.querySelector('#uploadSubmit'),
  renameButton: document.querySelector('#renameButton'),
  deleteButton: document.querySelector('#deleteButton'),
  title: document.querySelector('#configurationTitle'),
  empty: document.querySelector('#workflowEmpty'),
  metadataForm: document.querySelector('#metadataForm'),
  metadataStatus: document.querySelector('#metadataStatus'),
  metadataSubmit: document.querySelector('#metadataSubmit'),
  inputPorts: document.querySelector('#inputPorts'),
  outputPorts: document.querySelector('#outputPorts'),
  addInputPort: document.querySelector('#addInputPort'),
  addOutputPort: document.querySelector('#addOutputPort'),
  portTemplate: document.querySelector('#metadataPortTemplate'),
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
  elements.uploadButton.disabled = busy;
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

function renderConfiguration() {
  const workflow = selectedWorkflow();
  elements.empty.hidden = Boolean(workflow);
  elements.metadataForm.hidden = !workflow;
  elements.renameButton.hidden = !workflow;
  elements.deleteButton.hidden = !workflow;
  elements.title.textContent = workflow?.name || '选择一个 Workflow';
  if (!workflow) {
    elements.inputPorts.replaceChildren();
    elements.outputPorts.replaceChildren();
    return;
  }
  elements.metadataStatus.textContent = '';
  renderPortList(elements.inputPorts, workflow.input_ports || []);
  renderPortList(elements.outputPorts, workflow.output_ports || []);
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

function openRenameDialog() {
  const workflow = selectedWorkflow();
  if (!workflow) return;
  elements.renameName.value = workflow.name;
  elements.renameError.textContent = '';
  elements.renameDialog.showModal();
  elements.renameName.focus();
  elements.renameName.select();
}

function validateUploadName() {
  const name = elements.uploadName.value.trim();
  const duplicate = state.workflows.some((workflow) => workflow.name === name);
  elements.uploadError.textContent = !name ? 'Workflow 名称不能为空' : duplicate ? 'Workflow 名称已存在，请修改' : '';
  elements.uploadSubmit.disabled = !name || duplicate || state.saving;
  return Boolean(name) && !duplicate;
}

function resolveWorkflowReferences(imported) {
  const references = Array.isArray(imported.workflow_nodes) ? imported.workflow_nodes : [];
  const resolvedIds = new Map();
  const workflowNodes = references.map((reference) => {
    const referenceName = reference.name || reference.workflow_name || reference.workflow_id;
    const matches = state.workflows.filter((workflow) => workflow.id === reference.workflow_id || workflow.name === referenceName);
    if (matches.length !== 1) {
      throw new Error(matches.length ? `被调用 Workflow“${referenceName}”名称不唯一` : `找不到被调用 Workflow“${referenceName}”`);
    }
    resolvedIds.set(reference.workflow_id, matches[0]);
    resolvedIds.set(referenceName, matches[0]);
    return { workflow_id: matches[0].id };
  });
  const nodes = imported.nodes.map((node) => {
    if (node.type !== 'workflow') return node;
    const resolved = resolvedIds.get(node.workflow_id) || resolvedIds.get(node.workflow_name);
    if (!resolved) throw new Error(`节点“${node.name || node.id}”引用的 Workflow 不存在`);
    return { ...node, workflow_id: resolved.id, workflow_name: resolved.name };
  });
  return { workflowNodes, nodes };
}

async function chooseWorkflowFile() {
  const [file] = elements.uploadFileInput.files;
  elements.uploadFileInput.value = '';
  if (!file || state.saving) return;
  try {
    const imported = JSON.parse(await file.text());
    if (!imported || typeof imported !== 'object' || Array.isArray(imported)) throw new Error('文件不是有效的 Workflow JSON');
    if (typeof imported.name !== 'string' || !imported.name.trim()) throw new Error('Workflow 名称不能为空');
    if (!Array.isArray(imported.nodes) || !Array.isArray(imported.connections)) throw new Error('Workflow 缺少节点或连接数据');
    state.pendingUpload = imported;
    elements.uploadName.value = imported.name.trim();
    validateUploadName();
    elements.uploadDialog.showModal();
    elements.uploadName.focus();
    elements.uploadName.select();
  } catch (error) {
    state.pendingUpload = null;
    elements.state.textContent = error.message || '读取上传文件失败';
  }
}

async function confirmWorkflowUpload(event) {
  event.preventDefault();
  if (!state.pendingUpload || state.saving || !validateUploadName()) return;
  const imported = state.pendingUpload;
  const uploadName = elements.uploadName.value.trim();
  let created = null;
  state.saving = true;
  elements.uploadSubmit.disabled = true;
  elements.state.textContent = '上传中';
  updateControls();
  try {
    const { workflowNodes, nodes } = resolveWorkflowReferences(imported);
    created = await createWorkflow(uploadName);
    await updateWorkflowMetadata(created.id, imported.input_ports || [], imported.output_ports || [], workflowNodes);
    const uploaded = workflowSummary(await uploadWorkflow(created.id, {
      name: uploadName,
      version: Number.isInteger(imported.version) && imported.version >= 1 ? imported.version : 1,
      input_ports: imported.input_ports || [],
      output_ports: imported.output_ports || [],
      nodes,
      connections: imported.connections,
    }));
    state.workflows.unshift(uploaded);
    state.selectedId = uploaded.id;
    state.pendingUpload = null;
    elements.uploadDialog.close();
    elements.state.textContent = `已上传，共 ${state.workflows.length} 个`;
  } catch (error) {
    if (created) {
      try {
        await deleteWorkflow(created.id);
      } catch (cleanupError) {
        console.warn('上传失败后的 Workflow 清理失败', cleanupError);
      }
    }
    elements.state.textContent = error.name === 'AbortError' ? '上传超时' : (error.message || '上传失败');
  } finally {
    state.saving = false;
    validateUploadName();
    updateControls();
    renderList();
    renderConfiguration();
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
    localStorage.removeItem(`aagent.workflow.draft.v1.${workflow.id}`);
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
  const duplicateSide = [inputPorts, outputPorts].find((ports) => new Set(ports.map((port) => port.name)).size !== ports.length);
  if (duplicateSide) {
    elements.metadataStatus.textContent = '同一侧字段名不能重复';
    return;
  }
  state.saving = true;
  elements.metadataStatus.textContent = '保存中';
  updateControls();
  try {
    const updated = workflowSummary(await updateWorkflowMetadata(workflow.id, inputPorts, outputPorts));
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
elements.uploadButton.addEventListener('click', () => elements.uploadFileInput.click());
elements.uploadFileInput.addEventListener('change', chooseWorkflowFile);
elements.uploadName.addEventListener('input', validateUploadName);
elements.uploadForm.addEventListener('submit', confirmWorkflowUpload);
elements.uploadDialog.addEventListener('close', () => {
  if (!state.saving) state.pendingUpload = null;
});
elements.renameButton.addEventListener('click', openRenameDialog);
elements.deleteButton.addEventListener('click', removeSelectedWorkflow);
elements.addInputPort.addEventListener('click', () => appendPort(elements.inputPorts));
elements.addOutputPort.addEventListener('click', () => appendPort(elements.outputPorts));
elements.metadataForm.addEventListener('submit', submitMetadata);
elements.renameForm.addEventListener('submit', submitRename);
for (const button of document.querySelectorAll('[data-close-dialog]')) {
  button.addEventListener('click', () => {
    const dialog = button.closest('dialog');
    if (dialog === elements.uploadDialog) state.pendingUpload = null;
    dialog.close();
  });
}
loadWorkflows();