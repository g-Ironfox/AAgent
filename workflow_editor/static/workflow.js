import { fetchModels, fetchTools } from './api.js';
import { addNode, loadSnapshot, state, workflowSnapshot } from './workflow/model.js';
import { createConnectionController } from './workflow/connections.js';
import { createWorkflowView } from './workflow/view.js';

const elements = {
  canvas: document.querySelector('#workflowCanvas'),
  connectionLayer: document.querySelector('#connectionLayer'),
  nodeLayer: document.querySelector('#nodeLayer'),
  inspectorTitle: document.querySelector('#inspectorTitle'),
  inspectorType: document.querySelector('#inspectorType'),
  inspectorContent: document.querySelector('#inspectorContent'),
  nodeCount: document.querySelector('#nodeCount'),
  connectionCount: document.querySelector('#connectionCount'),
  workflowNodeLibrary: document.querySelector('#workflowNodeLibrary'),
  workflowState: document.querySelector('#workflowState'),
  importButton: document.querySelector('#importButton'),
  importFileInput: document.querySelector('#importFileInput'),
  exportButton: document.querySelector('#exportButton'),
  metadataButton: document.querySelector('#metadataButton'),
  metadataDialog: document.querySelector('#metadataDialog'),
  metadataForm: document.querySelector('#metadataForm'),
  workflowName: document.querySelector('#workflowName'),
  workflowSelect: document.querySelector('#workflowSelect'),
  metadataWorkflowSelect: document.querySelector('#metadataWorkflowSelect'),
  setMainWorkflowButton: document.querySelector('#setMainWorkflowButton'),
  addWorkflowButton: document.querySelector('#addWorkflowButton'),
  deleteWorkflowButton: document.querySelector('#deleteWorkflowButton'),
  resourceState: document.querySelector('#resourceState'),
};
let hasUnsavedChanges = false;
let currentKey = 'main';
let collection = {
  format: 'aagent-workflow-collection',
  main: currentKey,
  workflows: {},
};

function markChanged() {
  hasUnsavedChanges = true;
  elements.workflowState.textContent = '未保存';
  elements.workflowState.classList.remove('saved');
}

const connections = createConnectionController(elements, markChanged);
const view = createWorkflowView(elements, connections, markChanged);
connections.bindCanvasPan();

function renderWorkflow() {
  view.renderNodes();
  view.renderInspector();
  connections.renderConnections();
}

function saveCurrentWorkflow() {
  collection.workflows[currentKey] = workflowSnapshot();
}

function workflowReferences() {
  return Object.entries(collection.workflows)
    .filter(([key]) => key !== currentKey)
    .map(([key, workflow]) => ({
      workflow_id: key,
      name: key,
      input_ports: workflow.input_ports || [],
      output_ports: workflow.output_ports || [],
    }));
}

function createWorkflowOptions() {
  return Object.keys(collection.workflows).map((key) => {
    const option = document.createElement('option');
    option.value = key;
    option.textContent = key === collection.main ? `${key} (Main)` : key;
    return option;
  });
}

function renderWorkflowSelectors() {
  elements.workflowSelect.replaceChildren(...createWorkflowOptions());
  elements.workflowSelect.value = currentKey;
  elements.metadataWorkflowSelect.replaceChildren(...createWorkflowOptions());
  elements.metadataWorkflowSelect.value = currentKey;
  elements.setMainWorkflowButton.disabled = currentKey === collection.main;
  elements.deleteWorkflowButton.disabled = Object.keys(collection.workflows).length === 1;
}

function selectWorkflow(key) {
  if (key === currentKey || !collection.workflows[key]) return;
  saveCurrentWorkflow();
  currentKey = key;
  loadSnapshot(collection.workflows[key], { ...collection.workflows[key], name: key });
  view.setWorkflowNodes(workflowReferences());
  renderWorkflowSelectors();
  renderWorkflow();
}

function uniqueWorkflowKey(base = 'workflow') {
  const normalized = base.trim() || 'workflow';
  if (!collection.workflows[normalized]) return normalized;
  let suffix = 2;
  while (collection.workflows[`${normalized}-${suffix}`]) suffix += 1;
  return `${normalized}-${suffix}`;
}

function addWorkflow() {
  saveCurrentWorkflow();
  const key = uniqueWorkflowKey('workflow');
  const empty = {
    name: key,
    input_ports: [],
    output_ports: [],
    nodes: [
      { id: 'input', type: 'input', name: 'Input', x: 52, y: 238 },
      { id: 'output', type: 'output', name: 'Output', x: 310, y: 238 },
    ],
    connections: [
      { id: 'control-input-output', fromId: 'input', fromPortId: 'control-out', toId: 'output', toPortId: 'control-in', type: 'control' },
    ],
  };
  collection.workflows[key] = empty;
  currentKey = key;
  loadSnapshot(empty);
  view.setWorkflowNodes(workflowReferences());
  markChanged();
  renderWorkflowSelectors();
  renderWorkflow();
  renderMetadataDialog();
}

function deleteWorkflow(key) {
  if (Object.keys(collection.workflows).length === 1) {
    elements.workflowState.textContent = '集合至少保留一个 Workflow';
    return;
  }
  saveCurrentWorkflow();
  const callers = Object.entries(collection.workflows).filter(([owner, workflow]) => owner !== key && (workflow.nodes || []).some((node) => node.type === 'workflow' && node.workflow_id === key));
  if (callers.length) {
    elements.workflowState.textContent = `仍被 ${callers.map(([owner]) => owner).join('、')} 引用`;
    return;
  }
  if (!window.confirm(`删除 Workflow “${key}”？`)) return;
  delete collection.workflows[key];
  if (collection.main === key) collection.main = Object.keys(collection.workflows)[0];
  if (currentKey === key) {
    currentKey = collection.main;
    loadSnapshot(collection.workflows[currentKey], { ...collection.workflows[currentKey], name: currentKey });
  }
  view.setWorkflowNodes(workflowReferences());
  markChanged();
  renderWorkflowSelectors();
  renderWorkflow();
  renderMetadataDialog();
}

function renameCurrentWorkflow(nextKey) {
  if (nextKey === currentKey) return true;
  if (collection.workflows[nextKey]) {
    elements.resourceState.textContent = 'Workflow 名称已存在';
    return false;
  }
  saveCurrentWorkflow();
  const previousKey = currentKey;
  const renamedWorkflows = {};
  for (const [key, workflow] of Object.entries(collection.workflows)) {
    for (const node of workflow.nodes || []) {
      if (node.type === 'workflow' && node.workflow_id === previousKey) {
        node.workflow_id = nextKey;
        node.workflow_name = nextKey;
      }
    }
    renamedWorkflows[key === previousKey ? nextKey : key] = workflow;
  }
  collection.workflows = renamedWorkflows;
  if (collection.main === previousKey) collection.main = nextKey;
  currentKey = nextKey;
  state.name = nextKey;
  return true;
}

function syncWorkflowCallers(key) {
  const target = collection.workflows[key];
  if (!target) return;
  for (const workflow of Object.values(collection.workflows)) {
    for (const node of workflow.nodes || []) {
      if (node.type !== 'workflow' || node.workflow_id !== key) continue;
      node.workflow_name = key;
      node.name = key;
      node.input_ports = structuredClone(target.input_ports || []);
      node.output_ports = structuredClone(target.output_ports || []);
    }
  }
}

collection.workflows[currentKey] = workflowSnapshot();
loadSnapshot(collection.workflows[currentKey], { ...collection.workflows[currentKey], name: currentKey });
view.setWorkflowNodes(workflowReferences());
renderWorkflowSelectors();

Promise.all([fetchModels(), fetchTools()])
  .then(([models, tools]) => {
    view.setModels(models.items);
    view.setTools(tools.items);
    elements.resourceState.textContent = `${models.items.length} Models · ${tools.items.length} Tools`;
  })
  .catch((error) => {
    console.warn('数据库资源读取失败', error);
    elements.resourceState.textContent = error.message || '数据库资源读取失败';
  });

function createMetadataPortRow(port = {}) {
  const row = document.querySelector('#metadataPortTemplate').content.firstElementChild.cloneNode(true);
  row.querySelector('[data-metadata-port-name]').value = port.name || '';
  row.querySelector('[data-metadata-port-type]').value = port.type || 'content';
  row.querySelector('[data-remove-metadata-port]').addEventListener('click', () => row.remove());
  return row;
}

function renderMetadataPortList(collection) {
  const list = document.querySelector(`[data-metadata-port-list="${collection}"]`);
  list.replaceChildren(...state[collection].map(createMetadataPortRow));
  if (!state[collection].length) {
    const empty = document.createElement('p');
    empty.className = 'metadata-empty';
    empty.textContent = '暂无接口';
    list.append(empty);
  }
}

function renderMetadataDialog() {
  elements.workflowName.value = currentKey;
  renderMetadataPortList('input_ports');
  renderMetadataPortList('output_ports');
}

function readMetadataPorts(collection) {
  return [...document.querySelectorAll(`[data-metadata-port-list="${collection}"] .metadata-port-row`)].map((row) => ({
    name: row.querySelector('[data-metadata-port-name]').value.trim(),
    type: row.querySelector('[data-metadata-port-type]').value,
  }));
}

elements.metadataButton.addEventListener('click', () => {
  renderMetadataDialog();
  elements.metadataDialog.showModal();
});

elements.workflowSelect.addEventListener('change', () => selectWorkflow(elements.workflowSelect.value));
elements.metadataWorkflowSelect.addEventListener('change', () => {
  selectWorkflow(elements.metadataWorkflowSelect.value);
  renderMetadataDialog();
});
elements.addWorkflowButton.addEventListener('click', addWorkflow);
elements.deleteWorkflowButton.addEventListener('click', () => deleteWorkflow(currentKey));
elements.setMainWorkflowButton.addEventListener('click', () => {
  collection.main = currentKey;
  markChanged();
  renderWorkflowSelectors();
});

for (const button of document.querySelectorAll('[data-add-metadata-port]')) {
  button.addEventListener('click', () => {
    const list = document.querySelector(`[data-metadata-port-list="${button.dataset.addMetadataPort}"]`);
    list.querySelector('.metadata-empty')?.remove();
    const row = createMetadataPortRow();
    list.append(row);
    row.querySelector('input').focus();
  });
}

elements.metadataForm.addEventListener('submit', (event) => {
  if (event.submitter?.value === 'cancel') return;
  event.preventDefault();
  if (!elements.metadataForm.reportValidity()) return;
  const inputPorts = readMetadataPorts('input_ports');
  const outputPorts = readMetadataPorts('output_ports');
  if ([inputPorts, outputPorts].some((ports) => new Set(ports.map((port) => port.name)).size !== ports.length)) {
    elements.resourceState.textContent = '同一侧接口名称不能重复';
    return;
  }
  const nextKey = elements.workflowName.value.trim();
  if (!renameCurrentWorkflow(nextKey)) return;
  const snapshot = workflowSnapshot();
  const metadata = {
    name: nextKey,
    input_ports: inputPorts,
    output_ports: outputPorts,
  };
  loadSnapshot(snapshot, metadata);
  saveCurrentWorkflow();
  syncWorkflowCallers(currentKey);
  loadSnapshot(collection.workflows[currentKey], { ...collection.workflows[currentKey], name: currentKey });
  view.setWorkflowNodes(workflowReferences());
  markChanged();
  renderWorkflowSelectors();
  renderWorkflow();
  elements.metadataDialog.close();
});

document.querySelector('#workflowNodeLibrary').addEventListener('click', (event) => {
  const button = event.target.closest('[data-add-workflow-node]');
  if (!button) return;
  const reference = workflowReferences().find((workflow) => workflow.workflow_id === button.dataset.addWorkflowNode);
  if (!reference) return;
  addNode('workflow', reference);
  markChanged();
  renderWorkflow();
});

for (const button of document.querySelectorAll('[data-add-node]')) {
  button.addEventListener('click', () => {
    const nodeType = button.dataset.addNode;
    addNode(nodeType);
    markChanged();
    view.renderNodes();
    view.renderInspector();
  });
}

elements.importButton.addEventListener('click', () => {
  if (hasUnsavedChanges && !window.confirm('导入会覆盖当前未保存的 Workflow，确定继续吗？')) return;
  elements.importFileInput.click();
});

elements.importFileInput.addEventListener('change', async () => {
  const [file] = elements.importFileInput.files;
  elements.importFileInput.value = '';
  if (!file) return;
  try {
    const imported = JSON.parse(await file.text());
    const importedWorkflows = imported?.workflows && typeof imported.workflows === 'object' && !Array.isArray(imported.workflows)
      ? imported.workflows
      : { [imported.name || 'main']: imported };
    const keys = Object.keys(importedWorkflows);
    if (!keys.length || keys.some((key) => !key || !Array.isArray(importedWorkflows[key]?.nodes))) {
      throw new Error('文件不是有效的 Workflow 集合 JSON');
    }
    const main = typeof imported.main === 'string' && importedWorkflows[imported.main] ? imported.main : keys[0];
    const workflows = Object.fromEntries(Object.entries(importedWorkflows).map(([key, workflow]) => {
      const snapshot = { ...workflow };
      delete snapshot.version;
      return [key, snapshot];
    }));
    collection = {
      format: 'aagent-workflow-collection',
      main,
      workflows: structuredClone(workflows),
    };
    currentKey = main;
    if (!loadSnapshot(collection.workflows[currentKey], { ...collection.workflows[currentKey], name: currentKey })) throw new Error('Main Workflow 无效');
    view.setWorkflowNodes(workflowReferences());
    markChanged();
    renderWorkflowSelectors();
    renderWorkflow();
    elements.workflowState.textContent = '已导入';
  } catch (error) {
    elements.workflowState.textContent = error.message || '导入失败';
    elements.workflowState.classList.remove('saved');
  }
});

elements.exportButton.addEventListener('click', () => {
  saveCurrentWorkflow();
  const blob = new Blob([`${JSON.stringify(collection, null, 2)}\n`], { type: 'application/json;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  const filename = collection.main.replace(/[<>:"/\\|?*]+/g, '-').replace(/\s+/g, '-') || 'aagent-workflows';
  link.download = `${filename}-collection-${new Date().toISOString().slice(0, 10)}.json`;
  link.click();
  URL.revokeObjectURL(url);
});

window.addEventListener('beforeunload', (event) => {
  if (!hasUnsavedChanges) return;
  event.preventDefault();
  event.returnValue = '';
});

window.addEventListener('resize', connections.renderConnections);

renderWorkflow();
