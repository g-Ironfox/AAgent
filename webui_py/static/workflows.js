import { createWorkflow, deleteWorkflow, fetchWorkflow, fetchWorkflows, renameWorkflow, updateWorkflowMetadata, uploadWorkflow } from './api.js';

const state = { workflows: [], selectedId: null, loading: false, saving: false, pendingUpload: null, uploadMode: 'create' };
const elements = {
  state: document.querySelector('#workflowState'),
  list: document.querySelector('#workflowList'),
  uploadButton: document.querySelector('#uploadButton'),
  uploadFileInput: document.querySelector('#uploadFileInput'),
  textImportButton: document.querySelector('#textImportButton'),
  textImportDialog: document.querySelector('#textImportDialog'),
  textImportForm: document.querySelector('#textImportForm'),
  textImportValue: document.querySelector('#textImportValue'),
  textImportError: document.querySelector('#textImportError'),
  uploadDialog: document.querySelector('#uploadDialog'),
  uploadForm: document.querySelector('#uploadForm'),
  uploadName: document.querySelector('#uploadName'),
  uploadError: document.querySelector('#uploadError'),
  uploadSubmit: document.querySelector('#uploadSubmit'),
  uploadOverwrite: document.querySelector('#uploadOverwrite'),
  copyButton: document.querySelector('#copyButton'),
  exportButton: document.querySelector('#exportButton'),
  renameButton: document.querySelector('#renameButton'),
  deleteButton: document.querySelector('#deleteButton'),
  title: document.querySelector('#configurationTitle'),
  description: document.querySelector('#workflowDescription'),
  empty: document.querySelector('#workflowEmpty'),
  metadataPanel: document.querySelector('#metadataPanel'),
  inputPorts: document.querySelector('#inputPorts'),
  outputPorts: document.querySelector('#outputPorts'),
  dependencies: document.querySelector('#workflowDependencies'),
  dependencyCount: document.querySelector('#dependencyCount'),
  remoteTools: document.querySelector('#remoteTools'),
  remoteToolCount: document.querySelector('#remoteToolCount'),
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
  elements.uploadButton.disabled = busy;
  elements.textImportButton.disabled = busy;
  elements.copyButton.disabled = busy || !selected;
  elements.exportButton.disabled = busy || !selected;
  elements.renameButton.disabled = busy || !selected;
  elements.deleteButton.disabled = busy || !selected;
}

function createPortRow(port) {
  const row = elements.portTemplate.content.firstElementChild.cloneNode(true);
  row.querySelector('[data-port-name]').textContent = port.name || '未命名字段';
  row.querySelector('[data-port-type]').textContent = port.type || 'content';
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

function createDependencyContract(title, markerClass, ports) {
  const section = document.createElement('section');
  section.className = 'dependency-contract';
  const heading = document.createElement('h5');
  const marker = document.createElement('span');
  marker.className = `metadata-port-mark ${markerClass}`;
  marker.textContent = markerClass === 'input' ? 'IN' : 'OUT';
  heading.append(marker, title);
  const list = document.createElement('div');
  list.className = 'dependency-contract-ports';
  renderPortList(list, ports || []);
  section.append(heading, list);
  return section;
}

function samePortContract(leftPorts = [], rightPorts = []) {
  return JSON.stringify(leftPorts.map((port) => ({ name: port.name, type: port.type })))
    === JSON.stringify(rightPorts.map((port) => ({ name: port.name, type: port.type })));
}

function createContractWarning(reference, referenceName) {
  const target = state.workflows.find((workflow) => workflow.name === referenceName);
  if (!target) return null;
  const inputMatches = samePortContract(reference.input_ports, target.input_ports);
  const outputMatches = samePortContract(reference.output_ports, target.output_ports);
  if (inputMatches && outputMatches) return null;
  const warning = document.createElement('p');
  warning.className = 'dependency-contract-warning';
  const mismatches = [
    !inputMatches ? 'Input' : '',
    !outputMatches ? 'Output' : '',
  ].filter(Boolean).join('、');
  warning.textContent = `契约错误：${mismatches} 端口与对应 Workflow 不一致`;
  return warning;
}

function renderDependencies(references) {
  elements.dependencies.replaceChildren();
  elements.dependencyCount.textContent = `${references.length} 项`;
  if (!references.length) {
    const empty = document.createElement('p');
    empty.className = 'metadata-port-empty';
    empty.textContent = '无 Workflow 依赖';
    elements.dependencies.append(empty);
    return;
  }
  for (const reference of references) {
    const item = document.createElement('article');
    item.className = 'workflow-dependency-item';
    const heading = document.createElement('header');
    const identity = document.createElement('div');
    identity.className = 'workflow-dependency-identity';
    const marker = document.createElement('span');
    marker.className = 'metadata-port-mark workflow';
    marker.textContent = 'WF';
    const name = document.createElement('strong');
    const referenceName = reference.name || reference.workflow_name || '';
    name.textContent = referenceName || '未命名 Workflow';
    identity.append(marker, name);
    const editButton = document.createElement('button');
    editButton.type = 'button';
    editButton.className = 'dependency-edit-button';
    editButton.textContent = '修改';
    editButton.title = '修改依赖 Workflow';
    editButton.addEventListener('click', () => editDependency(item, references, referenceName));
    heading.append(identity, editButton);
    const contracts = document.createElement('div');
    contracts.className = 'dependency-contracts';
    contracts.append(
      createDependencyContract('Input', 'input', reference.input_ports),
      createDependencyContract('Output', 'output', reference.output_ports),
    );
    const warning = createContractWarning(reference, referenceName);
    item.append(heading);
    if (warning) item.append(warning);
    item.append(contracts);
    elements.dependencies.append(item);
  }
}

function renderRemoteTools(references) {
  elements.remoteTools.replaceChildren();
  elements.remoteToolCount.textContent = `${references.length} 项`;
  if (!references.length) {
    const empty = document.createElement('p');
    empty.className = 'metadata-port-empty';
    empty.textContent = '无 Remote Tool 依赖';
    elements.remoteTools.append(empty);
    return;
  }
  for (const reference of references) {
    const item = document.createElement('article');
    item.className = 'workflow-dependency-item';
    const heading = document.createElement('header');
    const identity = document.createElement('div');
    identity.className = 'workflow-dependency-identity';
    const marker = document.createElement('span');
    marker.className = 'metadata-port-mark remote-tool';
    marker.textContent = 'RT';
    const name = document.createElement('strong');
    name.textContent = reference.name || '未命名 Remote Tool';
    identity.append(marker, name);
    heading.append(identity);
    const contracts = document.createElement('div');
    contracts.className = 'dependency-contracts';
    contracts.append(
      createDependencyContract('Input', 'input', reference.input_ports),
      createDependencyContract('Output', 'output', reference.output_ports),
    );
    item.append(heading, contracts);
    elements.remoteTools.append(item);
  }
}

function editDependency(item, references, currentName) {
  if (state.saving) return;
  const heading = item.querySelector(':scope > header');
  const identity = item.querySelector('.workflow-dependency-identity');
  const input = document.createElement('input');
  input.className = 'dependency-name-input';
  input.type = 'text';
  input.value = currentName;
  input.maxLength = 120;
  input.setAttribute('aria-label', '输入依赖 Workflow 名称');
  const actions = document.createElement('span');
  actions.className = 'dependency-edit-actions';
  const saveButton = document.createElement('button');
  saveButton.type = 'button';
  saveButton.className = 'dependency-save-button';
  saveButton.textContent = '保存';
  const updateSaveState = () => {
    const name = input.value.trim();
    const exists = state.workflows.some((workflow) => workflow.id !== state.selectedId && workflow.name === name);
    const duplicate = references.some((reference) => {
      const referenceValue = reference.name || reference.workflow_name;
      return referenceValue !== currentName && referenceValue === name;
    });
    saveButton.disabled = !name || !exists || duplicate;
    input.classList.toggle('invalid', Boolean(name) && (!exists || duplicate));
  };
  const cancelButton = document.createElement('button');
  cancelButton.type = 'button';
  cancelButton.className = 'dependency-cancel-button';
  cancelButton.textContent = '取消';
  actions.append(saveButton, cancelButton);
  identity.replaceChildren(input);
  heading.replaceChildren(identity, actions);
  cancelButton.addEventListener('click', () => renderConfiguration());
  input.addEventListener('input', updateSaveState);
  saveButton.addEventListener('click', () => {
    if (input.value.trim() === currentName) {
      renderConfiguration();
      return;
    }
    saveDependency(references, currentName, input.value.trim());
  });
  updateSaveState();
  input.focus();
  input.select();
}

async function saveDependency(references, previousName, nextName) {
  const workflow = selectedWorkflow();
  if (!workflow || state.saving || !nextName || nextName === previousName) return;
  const target = state.workflows.find((item) => item.id !== workflow.id && item.name === nextName);
  if (!target) {
    elements.state.textContent = '依赖 Workflow 不存在，无法保存';
    return;
  }
  const nextReferences = references.map((reference) => ({
    name: (reference.name || reference.workflow_name) === previousName ? nextName : reference.name || reference.workflow_name,
    input_ports: reference.input_ports || [],
    output_ports: reference.output_ports || [],
    ...(reference.name === previousName || reference.workflow_name === previousName ? { previous_name: previousName } : {}),
  }));
  if (new Set(nextReferences.map((reference) => reference.name)).size !== nextReferences.length) {
    elements.state.textContent = '依赖 Workflow 不能重复';
    return;
  }
  state.saving = true;
  elements.state.textContent = '保存依赖中';
  updateControls();
  try {
    const updated = workflowSummary(await updateWorkflowMetadata(
      workflow.id,
      workflow.input_ports || [],
      workflow.output_ports || [],
      nextReferences,
      workflow.remote_tools || [],
    ));
    const index = state.workflows.findIndex((item) => item.id === workflow.id);
    state.workflows[index] = { ...state.workflows[index], ...updated };
    elements.state.textContent = '依赖已更新';
    renderList();
    renderConfiguration();
  } catch (error) {
    elements.state.textContent = error.name === 'AbortError' ? '保存依赖超时' : (error.message || '保存依赖失败');
  } finally {
    state.saving = false;
    updateControls();
  }
}

function renderConfiguration() {
  const workflow = selectedWorkflow();
  elements.empty.hidden = Boolean(workflow);
  elements.metadataPanel.hidden = !workflow;
  elements.copyButton.hidden = !workflow;
  elements.exportButton.hidden = !workflow;
  elements.renameButton.hidden = !workflow;
  elements.deleteButton.hidden = !workflow;
  elements.title.textContent = workflow?.name || '选择一个 Workflow';
  if (!workflow) {
    elements.description.textContent = '';
    elements.inputPorts.replaceChildren();
    elements.outputPorts.replaceChildren();
    elements.dependencies.replaceChildren();
    elements.dependencyCount.textContent = '';
    elements.remoteTools.replaceChildren();
    elements.remoteToolCount.textContent = '';
    return;
  }
  elements.description.textContent = workflow.description || '暂无描述';
  elements.description.classList.toggle('empty', !workflow.description);
  renderPortList(elements.inputPorts, workflow.input_ports || []);
  renderPortList(elements.outputPorts, workflow.output_ports || []);
  renderDependencies(workflow.workflow_nodes || []);
  renderRemoteTools(workflow.remote_tools || []);
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
  title.textContent = workflow.name || '未命名 Workflow';
    const meta = document.createElement('small');
    meta.textContent = `${workflow.node_count} 节点 / ${workflow.connection_count} 连接`;

  button.append(title, meta);
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
  validateRenameName();
  elements.renameDialog.showModal();
  elements.renameName.focus();
  elements.renameName.select();
}

function validateWorkflowName(input, error, submit, excludedWorkflowId = null) {
  const name = input.value.trim();
  const duplicate = state.workflows.some((workflow) => workflow.id !== excludedWorkflowId && workflow.name === name);
  error.textContent = !name ? 'Workflow 名称不能为空' : duplicate ? 'Workflow 名称已存在，可选择覆盖' : '';
  submit.disabled = !name || duplicate || state.saving;
  return Boolean(name) && !duplicate;
}

function validateUploadName() {
  const name = elements.uploadName.value.trim();
  const duplicate = state.workflows.some((workflow) => workflow.name === name);
  elements.uploadError.textContent = !name ? 'Workflow 名称不能为空' : duplicate ? 'Workflow 名称已存在，可选择覆盖' : '';
  elements.uploadSubmit.disabled = !name || duplicate || state.saving;
  elements.uploadOverwrite.disabled = !name || !duplicate || state.saving;
  state.uploadMode = duplicate ? 'overwrite' : 'create';
  return Boolean(name) && !duplicate;
}

function validateRenameName() {
  return validateWorkflowName(elements.renameName, elements.renameError, elements.renameSubmit, state.selectedId);
}

function resolveWorkflowReferences(imported) {
  const references = Array.isArray(imported.workflow_nodes) ? imported.workflow_nodes : [];
  const resolvedReferences = new Map();
  const workflowNodes = references.map((reference) => {
    const referenceName = reference.name || reference.workflow_name || reference.workflow_id;
    const matches = state.workflows.filter((workflow) => workflow.id === reference.workflow_id || workflow.name === referenceName);
    if (matches.length !== 1) {
      throw new Error(matches.length ? `被调用 Workflow“${referenceName}”名称不唯一` : `找不到被调用 Workflow“${referenceName}”`);
    }
    if (reference.workflow_id) resolvedReferences.set(reference.workflow_id, matches[0]);
    resolvedReferences.set(referenceName, matches[0]);
    return { name: matches[0].name };
  });
  const nodes = imported.nodes.map((node) => {
    if (node.type !== 'workflow') return node;
    const resolved = resolvedReferences.get(node.workflow_id) || resolvedReferences.get(node.workflow_name);
    if (!resolved) throw new Error(`节点“${node.name || node.id}”引用的 Workflow 不存在`);
    const { workflow_id, ...nameBasedNode } = node;
    return { ...nameBasedNode, workflow_name: resolved.name };
  });
  return { workflowNodes, nodes };
}

function parseWorkflowText(text) {
  const imported = JSON.parse(text);
  if (!imported || typeof imported !== 'object' || Array.isArray(imported)) throw new Error('内容不是有效的 Workflow JSON');
  if (typeof imported.name !== 'string' || !imported.name.trim()) throw new Error('Workflow 名称不能为空');
  if (!Array.isArray(imported.nodes) || !Array.isArray(imported.connections)) throw new Error('Workflow 缺少节点或连接数据');
  return imported;
}

function prepareWorkflowUpload(imported) {
  state.pendingUpload = imported;
  state.uploadMode = 'create';
  elements.uploadName.value = imported.name.trim();
  validateUploadName();
  elements.uploadDialog.showModal();
  elements.uploadName.focus();
  elements.uploadName.select();
}

async function chooseWorkflowFile() {
  const [file] = elements.uploadFileInput.files;
  elements.uploadFileInput.value = '';
  if (!file || state.saving) return;
  try {
    prepareWorkflowUpload(parseWorkflowText(await file.text()));
  } catch (error) {
    state.pendingUpload = null;
    elements.state.textContent = error.message || '读取上传文件失败';
  }
}

async function openTextImportDialog() {
  elements.textImportValue.value = '';
  elements.textImportError.textContent = '';
  elements.textImportDialog.showModal();
  if (navigator.clipboard?.readText) {
    try {
      const clipboardText = await navigator.clipboard.readText();
      parseWorkflowText(clipboardText);
      if (elements.textImportDialog.open && !elements.textImportValue.value) elements.textImportValue.value = clipboardText;
    } catch (error) {
      if (error.name !== 'NotAllowedError' && !(error instanceof SyntaxError)) console.debug('剪贴板中没有可导入的 Workflow', error);
    }
  }
  elements.textImportValue.focus();
}

function submitTextImport(event) {
  event.preventDefault();
  try {
    const imported = parseWorkflowText(elements.textImportValue.value);
    elements.textImportError.textContent = '';
    elements.textImportDialog.close();
    prepareWorkflowUpload(imported);
  } catch (error) {
    elements.textImportError.textContent = error.message || 'Workflow 文本无效';
  }
}

async function confirmWorkflowUpload(event) {
  event.preventDefault();
  if (!state.pendingUpload || state.saving || !validateUploadName()) return;
  const imported = state.pendingUpload;
  const uploadName = elements.uploadName.value.trim();
  const existing = state.workflows.find((workflow) => workflow.name === uploadName);
  let created = null;
  state.saving = true;
  elements.uploadSubmit.disabled = true;
  elements.state.textContent = '上传中';
  updateControls();
  try {
    const { workflowNodes, nodes } = resolveWorkflowReferences(imported);
    created = await createWorkflow(uploadName);
    await updateWorkflowMetadata(created.id, imported.input_ports || [], imported.output_ports || [], workflowNodes, imported.remote_tools || []);
    const uploaded = workflowSummary(await uploadWorkflow(created.id, {
      name: uploadName,
      description: typeof imported.description === 'string' ? imported.description : '',
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

async function overwriteWorkflow() {
  if (!state.pendingUpload || state.saving) return;
  const imported = state.pendingUpload;
  const uploadName = elements.uploadName.value.trim();
  const existing = state.workflows.find((workflow) => workflow.name === uploadName);
  if (!existing || !uploadName) return;
  state.saving = true;
  elements.uploadOverwrite.disabled = true;
  elements.uploadSubmit.disabled = true;
  elements.state.textContent = '覆盖中';
  updateControls();
  try {
    const { workflowNodes, nodes } = resolveWorkflowReferences(imported);
    await updateWorkflowMetadata(existing.id, imported.input_ports || [], imported.output_ports || [], workflowNodes, imported.remote_tools || []);
    const uploaded = workflowSummary(await uploadWorkflow(existing.id, {
      name: uploadName,
      description: typeof imported.description === 'string' ? imported.description : '',
      version: Number.isInteger(imported.version) && imported.version >= 1 ? imported.version : 1,
      input_ports: imported.input_ports || [],
      output_ports: imported.output_ports || [],
      nodes,
      connections: imported.connections,
    }));
    const index = state.workflows.findIndex((workflow) => workflow.id === existing.id);
    state.workflows[index] = uploaded;
    state.selectedId = uploaded.id;
    state.pendingUpload = null;
    elements.uploadDialog.close();
    elements.state.textContent = `已覆盖，共 ${state.workflows.length} 个`;
  } catch (error) {
    elements.state.textContent = error.name === 'AbortError' ? '覆盖超时' : (error.message || '覆盖失败');
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
  if (!workflow || state.saving || !elements.renameForm.reportValidity() || !validateRenameName()) return;
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

function exportableWorkflow(detail) {
  return {
    name: detail.name,
    description: detail.description || '',
    version: detail.version,
    input_ports: detail.input_ports || [],
    output_ports: detail.output_ports || [],
    workflow_nodes: detail.workflow_nodes || [],
    remote_tools: detail.remote_tools || [],
    nodes: detail.nodes || [],
    connections: detail.connections || [],
  };
}

async function writeClipboardText(text) {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text);
    return;
  }
  const textarea = document.createElement('textarea');
  textarea.value = text;
  textarea.setAttribute('readonly', '');
  textarea.style.position = 'fixed';
  textarea.style.opacity = '0';
  document.body.append(textarea);
  textarea.select();
  const copied = document.execCommand('copy');
  textarea.remove();
  if (!copied) throw new Error('浏览器不允许访问剪贴板');
}

async function copySelectedWorkflow() {
  const workflow = selectedWorkflow();
  if (!workflow || state.saving) return;
  state.saving = true;
  elements.state.textContent = '复制中';
  updateControls();
  try {
    const detail = await fetchWorkflow(workflow.id);
    await writeClipboardText(JSON.stringify(exportableWorkflow(detail)));
    elements.state.textContent = '已复制到剪贴板';
  } catch (error) {
    elements.state.textContent = error.name === 'AbortError' ? '复制超时' : (error.message || '复制失败');
  } finally {
    state.saving = false;
    updateControls();
  }
}

async function exportSelectedWorkflow() {
  const workflow = selectedWorkflow();
  if (!workflow || state.saving) return;
  state.saving = true;
  elements.state.textContent = '导出中';
  updateControls();
  try {
    const detail = await fetchWorkflow(workflow.id);
    const exported = exportableWorkflow(detail);
    const blob = new Blob([`${JSON.stringify(exported, null, 2)}\n`], { type: 'application/json;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    const filename = (detail.name || 'workflow').replace(/[<>:"/\\|?*]+/g, '-').replace(/\s+/g, '-');
    link.href = url;
    link.download = `${filename}-${new Date().toISOString().slice(0, 10)}.json`;
    link.click();
    URL.revokeObjectURL(url);
    elements.state.textContent = '已导出';
  } catch (error) {
    elements.state.textContent = error.name === 'AbortError' ? '导出超时' : (error.message || '导出失败');
  } finally {
    state.saving = false;
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

elements.uploadButton.addEventListener('click', () => elements.uploadFileInput.click());
elements.uploadFileInput.addEventListener('change', chooseWorkflowFile);
elements.textImportButton.addEventListener('click', openTextImportDialog);
elements.textImportForm.addEventListener('submit', submitTextImport);
elements.uploadName.addEventListener('input', validateUploadName);
elements.renameName.addEventListener('input', validateRenameName);
elements.uploadForm.addEventListener('submit', confirmWorkflowUpload);
elements.uploadOverwrite.addEventListener('click', overwriteWorkflow);
elements.uploadDialog.addEventListener('close', () => {
  if (!state.saving) {
    state.pendingUpload = null;
    state.uploadMode = 'create';
  }
});
elements.renameButton.addEventListener('click', openRenameDialog);
elements.copyButton.addEventListener('click', copySelectedWorkflow);
elements.exportButton.addEventListener('click', exportSelectedWorkflow);
elements.deleteButton.addEventListener('click', removeSelectedWorkflow);
elements.renameForm.addEventListener('submit', submitRename);
for (const button of document.querySelectorAll('[data-close-dialog]')) {
  button.addEventListener('click', () => {
    const dialog = button.closest('dialog');
    if (dialog === elements.uploadDialog) {
      state.pendingUpload = null;
      state.uploadMode = 'create';
    }
    dialog.close();
  });
}
loadWorkflows();