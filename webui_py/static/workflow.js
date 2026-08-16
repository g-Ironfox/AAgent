import { fetchModels, uploadWorkflow } from './api.js';
import { addNode, loadDraft, resetDraft, saveDraft, workflowSnapshot } from './workflow/model.js';
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
  saveButton: document.querySelector('#saveButton'),
  uploadButton: document.querySelector('#uploadButton'),
  resetButton: document.querySelector('#resetButton'),
};
let hasUnsavedChanges = false;

function markChanged() {
  hasUnsavedChanges = true;
  elements.workflowState.textContent = '未保存';
  elements.workflowState.classList.remove('saved');
}

function markSaved(message) {
  hasUnsavedChanges = false;
  elements.workflowState.textContent = message;
  elements.workflowState.classList.add('saved');
}

const connections = createConnectionController(elements, markChanged);
const view = createWorkflowView(elements, connections, markChanged);
connections.bindCanvasPan();

fetchModels()
  .then((response) => view.setModels(response.items))
  .catch((error) => console.warn('模型配置读取失败', error));

for (const button of document.querySelectorAll('[data-add-node]')) {
  button.addEventListener('click', () => {
    addNode(button.dataset.addNode);
    markChanged();
    view.renderNodes();
    view.renderInspector();
  });
}

elements.saveButton.addEventListener('click', () => {
  saveDraft();
  markSaved('已存浏览器');
});

elements.uploadButton.addEventListener('click', async () => {
  elements.uploadButton.disabled = true;
  elements.uploadButton.textContent = '上传中';
  try {
    saveDraft();
    await uploadWorkflow('main', { name: 'Agent 主控制流', ...workflowSnapshot() });
    markSaved('已上传');
  } catch (error) {
    elements.workflowState.textContent = error.message || '上传失败';
    elements.workflowState.classList.remove('saved');
  } finally {
    elements.uploadButton.disabled = false;
    elements.uploadButton.textContent = '上传';
  }
});

elements.resetButton.addEventListener('click', () => {
  if (!window.confirm('重置会删除已保存的本地草稿，确定继续吗？')) return;
  resetDraft();
  markChanged();
  view.renderNodes();
  view.renderInspector();
});

window.addEventListener('beforeunload', (event) => {
  if (!hasUnsavedChanges) return;
  event.preventDefault();
  event.returnValue = '';
});

for (const link of document.querySelectorAll('.page-nav a, .brand')) {
  link.addEventListener('click', (event) => {
    if (!hasUnsavedChanges || window.confirm('当前 Workflow 有未保存修改，确定离开吗？')) {
      hasUnsavedChanges = false;
      return;
    }
    event.preventDefault();
  });
}

window.addEventListener('resize', connections.renderConnections);

if (loadDraft()) markSaved('已载入草稿');
view.renderNodes();
view.renderInspector();
