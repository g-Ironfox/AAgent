import { addNode, loadDraft, resetDraft, saveDraft } from './workflow/model.js';
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
  resetButton: document.querySelector('#resetButton'),
};

function markChanged() {
  elements.workflowState.textContent = '未保存';
  elements.workflowState.classList.remove('saved');
}

function markSaved(message) {
  elements.workflowState.textContent = message;
  elements.workflowState.classList.add('saved');
}

const connections = createConnectionController(elements, markChanged);
const view = createWorkflowView(elements, connections, markChanged);

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

elements.resetButton.addEventListener('click', () => {
  resetDraft();
  markChanged();
  view.renderNodes();
  view.renderInspector();
});

window.addEventListener('resize', connections.renderConnections);

if (loadDraft()) markSaved('已载入草稿');
view.renderNodes();
view.renderInspector();
