import { fetchModels, fetchTools, fetchWorkflows } from './api.js';
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
  workflowState: document.querySelector('#workflowState'),
  importButton: document.querySelector('#importButton'),
  importFileInput: document.querySelector('#importFileInput'),
  exportButton: document.querySelector('#exportButton'),
  metadataButton: document.querySelector('#metadataButton'),
  metadataDialog: document.querySelector('#metadataDialog'),
  metadataForm: document.querySelector('#metadataForm'),
  workflowName: document.querySelector('#workflowName'),
  workflowVersion: document.querySelector('#workflowVersion'),
  metadataWorkflowList: document.querySelector('#metadataWorkflowList'),
  resourceState: document.querySelector('#resourceState'),
};
let hasUnsavedChanges = false;
let availableWorkflows = [];

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

Promise.all([fetchModels(), fetchTools(), fetchWorkflows()])
  .then(([models, tools, workflows]) => {
    availableWorkflows = workflows.items;
    view.setModels(models.items);
    view.setTools(tools.items);
    view.setWorkflowNodes(availableWorkflows);
    elements.resourceState.textContent = `${models.items.length} Models · ${tools.items.length} Tools · ${availableWorkflows.length} Workflows`;
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
  elements.workflowName.value = state.name;
  elements.workflowVersion.value = state.version;
  renderMetadataPortList('input_ports');
  renderMetadataPortList('output_ports');
  const selectedIds = new Set(state.workflow_nodes.map((workflow) => workflow.workflow_id));
  elements.metadataWorkflowList.replaceChildren(...availableWorkflows.map((workflow) => {
    const label = document.createElement('label');
    label.className = 'metadata-workflow-option';
    label.innerHTML = '<input type="checkbox"><span><strong></strong><small></small></span>';
    label.querySelector('input').value = workflow.workflow_id;
    label.querySelector('input').checked = selectedIds.has(workflow.workflow_id);
    label.querySelector('strong').textContent = workflow.name || workflow.workflow_id;
    label.querySelector('small').textContent = `${workflow.input_ports.length} 输入 / ${workflow.output_ports.length} 输出`;
    return label;
  }));
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
  const selectedIds = new Set([...elements.metadataWorkflowList.querySelectorAll('input:checked')].map((input) => input.value));
  const workflowNodes = availableWorkflows.filter((workflow) => selectedIds.has(workflow.workflow_id));
  const snapshot = workflowSnapshot();
  const metadata = {
    name: elements.workflowName.value.trim(),
    version: Number.parseInt(elements.workflowVersion.value, 10),
    input_ports: inputPorts,
    output_ports: outputPorts,
    workflow_nodes: workflowNodes,
  };
  loadSnapshot(snapshot, metadata);
  view.setWorkflowNodes(workflowNodes);
  markChanged();
  renderWorkflow();
  elements.metadataDialog.close();
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
    const snapshot = JSON.parse(await file.text());
    if (!loadSnapshot(snapshot)) throw new Error('文件不是有效的 Workflow JSON');
    view.setWorkflowNodes(state.workflow_nodes);
    markChanged();
    view.renderNodes();
    view.renderInspector();
    elements.workflowState.textContent = '已导入';
  } catch (error) {
    elements.workflowState.textContent = error.message || '导入失败';
    elements.workflowState.classList.remove('saved');
  }
});

elements.exportButton.addEventListener('click', () => {
  const blob = new Blob([`${JSON.stringify(workflowSnapshot(), null, 2)}\n`], { type: 'application/json;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  const filename = state.name.trim().replace(/[<>:"/\\|?*]+/g, '-').replace(/\s+/g, '-') || 'aagent-workflow';
  link.download = `${filename}-${new Date().toISOString().slice(0, 10)}.json`;
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
