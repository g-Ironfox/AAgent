import { fetchLocalTools, fetchModels, fetchRemoteTools } from './api.js';
import { createWorkflowEditor } from './workflow/editor.js';
import { createInspector } from './workflow/inspector/inspector.js';
import { setRuntimeStyles } from './workflow/domain/runtime-styles.js';
import {
  addNode,
  loadSnapshot,
  parseWorkflowText,
  resetWorkflow,
  state,
  workflowSnapshot,
  validateStructDefinitions,
} from './workflow/domain/serialization.js';

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
  textImportButton: document.querySelector('#textImportButton'),
  textImportDialog: document.querySelector('#textImportDialog'),
  textImportValue: document.querySelector('#textImportValue'),
  textImportError: document.querySelector('#textImportError'),
  closeTextImportButton: document.querySelector('#closeTextImportButton'),
  overwriteTextImportButton: document.querySelector('#overwriteTextImportButton'),
  openTextImportButton: document.querySelector('#openTextImportButton'),
  cancelTextImportButton: document.querySelector('#cancelTextImportButton'),
  copyButton: document.querySelector('#copyButton'),
  exportButton: document.querySelector('#exportButton'),
  clearButton: document.querySelector('#clearButton'),
  metadataButton: document.querySelector('#metadataButton'),
  metadataDialog: document.querySelector('#metadataDialog'),
  metadataForm: document.querySelector('#metadataForm'),
  workflowName: document.querySelector('#workflowName'),
  workflowDescription: document.querySelector('#workflowDescription'),
  structDefinitions: document.querySelector('#structDefinitions'),
  structDefinitionsError: document.querySelector('#structDefinitionsError'),
  addStructButton: document.querySelector('#addStructButton'),
  canvasLegend: document.querySelector('#canvasLegend'),
  workflowNameDisplay: document.querySelector('#workflowNameDisplay'),
  callableWorkflowList: document.querySelector('#callableWorkflowList'),
  addCallableWorkflowButton: document.querySelector('#addCallableWorkflowButton'),
  remoteToolList: document.querySelector('#remoteToolList'),
  addRemoteToolButton: document.querySelector('#addRemoteToolButton'),
  resourceState: document.querySelector('#resourceState'),
};
let hasUnsavedChanges = false;
const undoHistory = [];
let lastUndoSnapshot = null;

function resetUndoHistory(snapshot = workflowSnapshot()) {
  undoHistory.length = 0;
  lastUndoSnapshot = structuredClone(snapshot);
}

function markChanged() {
  if (lastUndoSnapshot) {
    undoHistory.push(lastUndoSnapshot);
    if (undoHistory.length > 100) undoHistory.shift();
  }
  lastUndoSnapshot = workflowSnapshot();
  hasUnsavedChanges = true;
  elements.workflowState.textContent = '未保存';
  elements.workflowState.classList.remove('saved');
}

const editor = createWorkflowEditor(elements, markChanged);
const inspector = createInspector(elements, editor, markChanged);
let remoteToolSchemas = [];
let structDraft = [];
let structIdSequence = 0;
const structColors = ['#3A7D68', '#D97706', '#3976A8', '#B94E42', '#7A5AA6', '#56813B'];

function renderWorkflow() {
  renderStructLegend();
  editor.renderWorkflow();
}

function renderStructLegend() {
  const mount = elements.canvasLegend?.querySelector('[data-struct-legend]');
  if (!mount) return;
  mount.replaceChildren(...(state.metadata?.structs || []).map((definition) => {
    const item = document.createElement('span');
    const swatch = document.createElement('i');
    setRuntimeStyles(swatch, `struct-legend:${definition.id}`, { backgroundColor: definition.color });
    const name = document.createElement('span');
    name.textContent = `${definition.name} / ${definition.id}`;
    item.append(swatch, name);
    return item;
  }));
}

function currentCanvasViewport() {
  return {
    left: elements.canvas.scrollLeft,
    top: elements.canvas.scrollTop,
    width: elements.canvas.clientWidth,
    height: elements.canvas.clientHeight,
  };
}

function importWorkflowText(text, source = '已导入') {
  const workflow = parseWorkflowText(text);
  if (!loadSnapshot(workflow)) throw new Error('内容不是有效的 Workflow JSON');
  inspector.setWorkflowNodes(workflowReferences());
  inspector.setRemoteToolReferences(remoteToolReferences());
  resetUndoHistory();
  hasUnsavedChanges = true;
  elements.workflowNameDisplay.textContent = state.name;
  renderWorkflow();
  elements.workflowState.textContent = source;
  elements.workflowState.classList.remove('saved');
}

function isPristineEditor() {
  return !hasUnsavedChanges
    && state.name === 'workflow'
    && state.description === ''
    && state.input_ports.length === 0
    && state.output_ports.length === 0
    && state.workflow_nodes.length === 0
    && state.remote_tools.length === 0
    && state.nodes.length === 2
    && state.connections.length === 1;
}

async function writeClipboardText(text) {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text);
    return;
  }
  const textarea = document.createElement('textarea');
  textarea.value = text;
  textarea.setAttribute('readonly', '');
  textarea.className = 'clipboard-fallback';
  document.body.append(textarea);
  textarea.select();
  const copied = document.execCommand('copy');
  textarea.remove();
  if (!copied) throw new Error('浏览器不允许访问剪贴板');
}

function workflowReferences() {
  return state.workflow_nodes.map((workflow) => ({
      name: workflow.name,
      input_ports: workflow.input_ports || [],
      output_ports: workflow.output_ports || [],
    }));
}

function remoteToolReferences() {
  return state.remote_tools.map((tool) => ({
    name: tool.name,
    input_ports: tool.input_ports || [],
    output_ports: tool.output_ports || [],
  }));
}

loadSnapshot(workflowSnapshot());
inspector.setWorkflowNodes(workflowReferences());
inspector.setRemoteToolReferences(remoteToolReferences());
elements.workflowNameDisplay.textContent = state.name;
resetUndoHistory();

document.addEventListener('keydown', (event) => {
  if (!(event.ctrlKey || event.metaKey) || event.key.toLowerCase() !== 'z' || event.shiftKey) return;
  const target = event.target;
  if (target instanceof HTMLElement && (
    target.isContentEditable
    || target.closest('input, textarea, select, [contenteditable="true"], dialog')
  )) return;
  const snapshot = undoHistory.at(-1);
  if (!snapshot || !loadSnapshot(snapshot)) return;
  undoHistory.pop();
  event.preventDefault();
  lastUndoSnapshot = workflowSnapshot();
  hasUnsavedChanges = true;
  elements.workflowState.textContent = '未保存';
  elements.workflowState.classList.remove('saved');
  elements.workflowNameDisplay.textContent = state.name;
  inspector.setWorkflowNodes(workflowReferences());
  inspector.setRemoteToolReferences(remoteToolReferences());
  editor.ensureSelection();
  renderWorkflow();
});

const resourceCounts = { models: null, localTools: null, remoteTools: null };
const resourceErrors = {};

function renderResourceState() {
  const counts = [
    resourceCounts.models === null ? null : `${resourceCounts.models} Models`,
    resourceCounts.localTools === null ? null : `${resourceCounts.localTools} Local Tools`,
    resourceCounts.remoteTools === null ? null : `${resourceCounts.remoteTools} Remote Tools`,
  ].filter(Boolean);
  const errors = Object.values(resourceErrors);
  elements.resourceState.textContent = [...counts, ...errors].join(' · ') || '资源读取中';
}

fetchModels()
  .then((models) => {
    inspector.setModels(models.items);
    resourceCounts.models = models.items.length;
    renderResourceState();
  })
  .catch((error) => {
    console.warn('模型配置读取失败', error);
    resourceErrors.models = `Models: ${error.message || '读取失败'}`;
    renderResourceState();
  });

fetchLocalTools()
  .then((tools) => {
    inspector.setLocalTools(tools.items);
    resourceCounts.localTools = tools.items.length;
    renderResourceState();
  })
  .catch((error) => {
    console.warn('Local Tool 注册表读取失败', error);
    resourceErrors.localTools = `Local Tools: ${error.message || '读取失败'}`;
    renderResourceState();
  });

fetchRemoteTools()
  .then((tools) => {
    remoteToolSchemas = tools.items;
    document.querySelectorAll('.remote-tool-metadata-row').forEach((row) => renderRemoteToolSuggestions(row));
    resourceCounts.remoteTools = tools.items.length;
    renderResourceState();
  })
  .catch((error) => {
    console.warn('Remote Tool 目录读取失败', error);
    resourceErrors.remoteTools = `Remote Tools: ${error.message || '读取失败'}`;
    renderResourceState();
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
  elements.workflowDescription.value = state.description;
  renderMetadataPortList('input_ports');
  renderMetadataPortList('output_ports');
  structDraft = structuredClone(state.metadata?.structs || []);
  renderStructDefinitions();
  elements.structDefinitionsError.textContent = '';
  renderCallableWorkflowList();
  renderRemoteToolList();
}

function renderStructDefinitions() {
  const mount = elements.structDefinitions;
  mount.classList.toggle('is-empty', !structDraft.length);
  if (!structDraft.length) {
    const empty = document.createElement('div');
    empty.className = 'struct-definition-empty';
    empty.innerHTML = `
      <span class="struct-empty-icon" aria-hidden="true">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
          <rect x="4" y="3" width="16" height="18" rx="2"/>
          <path d="M8 8h8M11 12h5M11 16h5M8 12h.01M8 16h.01"/>
        </svg>
      </span>
      <div class="struct-empty-copy">
        <h4>创建第一个 Struct</h4>
        <p>将相关字段组合为可复用的数据类型，仅在当前 Workflow 内有效。</p>
      </div>
      <button class="struct-empty-create" type="button"><span aria-hidden="true">+</span> 创建 Struct</button>
    `;
    empty.querySelector('button').addEventListener('click', addStructDefinition);
    mount.replaceChildren(empty);
    return;
  }

  mount.replaceChildren(...structDraft.map((definition) => {
    const card = document.createElement('article');
    card.className = 'struct-definition';

    const header = document.createElement('div');
    header.className = 'struct-definition-head';
    const name = document.createElement('input');
    name.type = 'text';
    name.maxLength = 80;
    name.required = true;
    name.value = definition.name;
    name.placeholder = '显示名称';
    name.setAttribute('aria-label', 'Struct 显示名称');
    name.addEventListener('input', () => { definition.name = name.value; });
    const color = document.createElement('input');
    color.type = 'color';
    color.value = definition.color;
    color.setAttribute('aria-label', 'Struct 类型颜色');
    color.addEventListener('input', () => { definition.color = color.value.toUpperCase(); });
    const remove = document.createElement('button');
    remove.type = 'button';
    remove.className = 'struct-definition-remove';
    remove.title = '删除 Struct';
    remove.setAttribute('aria-label', `删除 ${definition.name}`);
    remove.textContent = '×';
    remove.addEventListener('click', () => {
      structDraft = structDraft.filter((item) => item !== definition);
      renderStructDefinitions();
    });
    const id = document.createElement('code');
    id.className = 'struct-definition-id';
    id.textContent = `ID: ${definition.id}`;
    header.append(name, color, remove, id);

    const fields = document.createElement('div');
    fields.className = 'struct-definition-fields';
    const fieldHeading = document.createElement('div');
    fieldHeading.className = 'struct-field-heading';
    fieldHeading.innerHTML = '<span>字段名</span><span>字段类型</span><span>必需</span><span>操作</span>';
    fields.append(fieldHeading);
    if (!definition.fields.length) {
      const empty = document.createElement('p');
      empty.className = 'struct-fields-empty';
      empty.textContent = '暂无字段，添加字段后即可定义该 Struct 的数据结构。';
      fields.append(empty);
    }
    for (const field of definition.fields) {
      const row = document.createElement('div');
      row.className = 'struct-field';
      const fieldName = document.createElement('input');
      fieldName.type = 'text';
      fieldName.maxLength = 80;
      fieldName.required = true;
      fieldName.value = field.name;
      fieldName.placeholder = '字段名';
      fieldName.setAttribute('aria-label', '字段名');
      fieldName.addEventListener('input', () => { field.name = fieldName.value; });

      const type = document.createElement('select');
      type.setAttribute('aria-label', `${field.name} 字段类型`);
      for (const builtin of ['content', 'message', 'event', 'map-content', 'list-content', 'list-message', 'list-event']) {
        type.add(new Option(builtin, builtin));
      }
      for (const target of structDraft) {
        type.add(new Option(`${target.name} (${target.id})`, `struct:${target.id}`));
        type.add(new Option(`List<${target.name}>`, `list-struct:${target.id}`));
      }
      if (![...type.options].some((option) => option.value === field.type)) type.add(new Option(field.type, field.type));
      type.value = field.type;
      type.addEventListener('change', () => { field.type = type.value; });

      const requiredLabel = document.createElement('label');
      requiredLabel.className = 'struct-field-required';
      const required = document.createElement('input');
      required.type = 'checkbox';
      required.checked = field.required;
      required.setAttribute('aria-label', `${field.name} 必需`);
      required.addEventListener('change', () => { field.required = required.checked; });
      requiredLabel.append(required, document.createTextNode('必需'));

      const removeField = document.createElement('button');
      removeField.type = 'button';
      removeField.className = 'struct-field-remove';
      removeField.title = '删除字段';
      removeField.setAttribute('aria-label', `删除字段 ${field.name}`);
      removeField.textContent = '×';
      removeField.addEventListener('click', () => {
        definition.fields = definition.fields.filter((item) => item !== field);
        renderStructDefinitions();
      });
      row.append(fieldName, type, requiredLabel, removeField);
      fields.append(row);
    }

    const actions = document.createElement('div');
    actions.className = 'struct-editor-actions';
    const fieldCount = document.createElement('span');
    fieldCount.className = 'struct-field-count';
    fieldCount.textContent = `${definition.fields.length} 个字段`;
    const addField = document.createElement('button');
    addField.type = 'button';
    addField.className = 'struct-add-field';
    addField.innerHTML = '<span aria-hidden="true">+</span> 添加字段';
    addField.addEventListener('click', () => {
      let index = definition.fields.length + 1;
      while (definition.fields.some((field) => field.name === `field_${index}`)) index += 1;
      definition.fields.push({ name: `field_${index}`, type: 'content', required: true });
      renderStructDefinitions();
    });
    actions.append(fieldCount, addField);
    card.append(header, fields, actions);
    return card;
  }));
}

function addStructDefinition() {
  structIdSequence += 1;
  const id = `struct_${Date.now().toString(36)}_${structIdSequence.toString(36)}`;
  let index = structDraft.length + 1;
  while (structDraft.some((definition) => definition.name === `Struct ${index}`)) index += 1;
  structDraft.push({
    id,
    name: `Struct ${index}`,
    color: structColors[(structDraft.length) % structColors.length],
    fields: [{ name: 'field_1', type: 'content', required: true }],
  });
  elements.structDefinitionsError.textContent = '';
  renderStructDefinitions();
  const nameInput = elements.structDefinitions.lastElementChild.querySelector('input[type="text"]');
  nameInput.focus();
  nameInput.select();
}

function readMetadataPorts(collection) {
  return [...document.querySelectorAll(`[data-metadata-port-list="${collection}"] .metadata-port-row`)].map((row) => ({
    name: row.querySelector('[data-metadata-port-name]').value.trim(),
    type: row.querySelector('[data-metadata-port-type]').value,
  }));
}

function renderCallablePortList(row, collection, ports) {
  const list = row.querySelector(`[data-callable-port-list="${collection}"]`);
  list.replaceChildren(...ports.map(createMetadataPortRow));
  if (!ports.length) {
    const empty = document.createElement('p');
    empty.className = 'metadata-empty';
    empty.textContent = '暂无接口';
    list.append(empty);
  }
}

function createCallableWorkflowRow(workflow = { name: '', input_ports: [], output_ports: [] }) {
  const row = document.querySelector('#callableWorkflowTemplate').content.firstElementChild.cloneNode(true);
  row.dataset.previousName = workflow.name || '';
  row.querySelector('[data-callable-workflow-name]').value = workflow.name || '';
  renderCallablePortList(row, 'input_ports', workflow.input_ports || []);
  renderCallablePortList(row, 'output_ports', workflow.output_ports || []);
  row.querySelector('[data-remove-callable-workflow]').addEventListener('click', () => row.remove());
  for (const button of row.querySelectorAll('[data-add-callable-port]')) {
    button.addEventListener('click', () => {
      const list = row.querySelector(`[data-callable-port-list="${button.dataset.addCallablePort}"]`);
      list.querySelector('.metadata-empty')?.remove();
      const portRow = createMetadataPortRow();
      list.append(portRow);
      portRow.querySelector('input').focus();
    });
  }
  return row;
}

function renderCallableWorkflowList() {
  elements.callableWorkflowList.replaceChildren(...state.workflow_nodes.map(createCallableWorkflowRow));
  if (!state.workflow_nodes.length) {
    const empty = document.createElement('p');
    empty.className = 'metadata-empty';
    empty.textContent = '暂无可调用 Workflow';
    elements.callableWorkflowList.append(empty);
  }
}

function readCallableWorkflows() {
  return [...elements.callableWorkflowList.querySelectorAll('.callable-workflow-row')].map((row) => ({
    previous_name: row.dataset.previousName,
    name: row.querySelector('[data-callable-workflow-name]').value.trim(),
    input_ports: readPortsFromList(row.querySelector('[data-callable-port-list="input_ports"]')),
    output_ports: readPortsFromList(row.querySelector('[data-callable-port-list="output_ports"]')),
  }));
}

function createRemoteToolRow(tool = { name: '', input_ports: [], output_ports: [] }) {
  const row = document.querySelector('#remoteToolMetadataTemplate').content.firstElementChild.cloneNode(true);
  row.dataset.previousName = tool.name || '';
  const nameInput = row.querySelector('[data-remote-tool-name]');
  nameInput.value = tool.name || '';
  renderRemoteToolSuggestions(row);
  renderCallablePortList(row, 'input_ports', tool.input_ports || []);
  renderCallablePortList(row, 'output_ports', tool.output_ports || []);
  row.querySelector('[data-remove-remote-tool]').addEventListener('click', () => row.remove());
  const fillFromSchema = (schema) => {
    if (!schema) {
      elements.resourceState.textContent = 'Tool Server 中没有同名 Remote Tool';
      return;
    }
    const schemaPorts = (schemaValue, defaultName = null) => {
      if (!schemaValue || typeof schemaValue !== 'object') return [];
      const workflowType = (value) => ['content', 'message', 'event', 'list-content', 'list-message', 'list-event'].includes(value?.['x-workflow-port-type'])
        ? value['x-workflow-port-type']
        : value?.type === 'array' ? 'list-content' : 'content';
      if (schemaValue.properties && typeof schemaValue.properties === 'object') {
        return Object.entries(schemaValue.properties).map(([name, value]) => ({ name, type: workflowType(value) }));
      }
      return defaultName ? [{ name: defaultName, type: workflowType(schemaValue) }] : [];
    };
    renderCallablePortList(row, 'input_ports', schemaPorts(schema.inputSchema));
    renderCallablePortList(row, 'output_ports', schemaPorts(schema.outputSchema, 'result'));
  };
  const selectSchema = (schema) => {
    if (!schema) return;
    nameInput.value = schema.name;
    fillFromSchema(schema);
    row.querySelector('[data-remote-tool-suggestions]').hidden = true;
  };
  nameInput.addEventListener('input', () => renderRemoteToolSuggestions(row));
  nameInput.addEventListener('focus', () => renderRemoteToolSuggestions(row));
  row.querySelector('[data-remote-tool-suggestions]').addEventListener('mousedown', (event) => {
    const option = event.target.closest('[data-remote-tool-suggestion]');
    if (!option) return;
    event.preventDefault();
    selectSchema(remoteToolSchemas.find((candidate) => candidate.name === option.dataset.remoteToolSuggestion));
  });
  row.querySelector('[data-fill-remote-tool]').addEventListener('click', () => {
    fillFromSchema(remoteToolSchemas.find((candidate) => candidate.name === nameInput.value.trim()));
  });
  for (const button of row.querySelectorAll('[data-add-callable-port]')) {
    button.addEventListener('click', () => {
      const list = row.querySelector(`[data-callable-port-list="${button.dataset.addCallablePort}"]`);
      list.querySelector('.metadata-empty')?.remove();
      list.append(createMetadataPortRow());
    });
  }
  return row;
}

function renderRemoteToolSuggestions(row) {
  const input = row.querySelector('[data-remote-tool-name]');
  const suggestions = row.querySelector('[data-remote-tool-suggestions]');
  const query = input.value.trim().toLocaleLowerCase();
  const matches = remoteToolSchemas.filter((tool) => `${tool.name} ${tool.description || ''}`.toLocaleLowerCase().includes(query)).slice(0, 8);
  suggestions.replaceChildren(...matches.map((tool) => {
    const option = document.createElement('button');
    option.type = 'button';
    option.className = 'remote-tool-suggestion';
    option.dataset.remoteToolSuggestion = tool.name;
    option.setAttribute('role', 'option');
    const name = document.createElement('strong');
    name.textContent = tool.name;
    const description = document.createElement('span');
    description.textContent = tool.description || '无描述';
    option.append(name, description);
    return option;
  }));
  suggestions.hidden = matches.length === 0 || document.activeElement !== input;
}

function renderRemoteToolList() {
  elements.remoteToolList.replaceChildren(...state.remote_tools.map(createRemoteToolRow));
  if (!state.remote_tools.length) {
    elements.remoteToolList.append(Object.assign(document.createElement('p'), { className: 'metadata-empty', textContent: '暂无 Remote Tool' }));
  }
}

function readRemoteTools() {
  return [...elements.remoteToolList.querySelectorAll('.remote-tool-metadata-row')].map((row) => ({
    previous_name: row.dataset.previousName,
    name: row.querySelector('[data-remote-tool-name]').value.trim(),
    input_ports: readPortsFromList(row.querySelector('[data-callable-port-list="input_ports"]')),
    output_ports: readPortsFromList(row.querySelector('[data-callable-port-list="output_ports"]')),
  }));
}

function readPortsFromList(list) {
  return [...list.querySelectorAll('.metadata-port-row')].map((row) => ({
    name: row.querySelector('[data-metadata-port-name]').value.trim(),
    type: row.querySelector('[data-metadata-port-type]').value,
  }));
}

function syncCallableWorkflowNodes(nextWorkflows) {
  const nextByPreviousName = new Map(nextWorkflows.map((workflow) => [workflow.previous_name || workflow.name, workflow]));
  for (const node of state.nodes) {
    if (node.type !== 'workflow') continue;
    const workflow = nextByPreviousName.get(node.workflow_name);
    if (!workflow) continue;
    node.workflow_name = workflow.name;
    node.name = workflow.name;
    node.input_ports = structuredClone(workflow.input_ports);
    node.output_ports = structuredClone(workflow.output_ports);
  }
}

function syncRemoteToolNodes(nextTools) {
  const nextByPreviousName = new Map(nextTools.map((tool) => [tool.previous_name || tool.name, tool]));
  for (const node of state.nodes) {
    if (!['remote_sync_tool', 'remote_async_tool'].includes(node.type)) continue;
    const tool = nextByPreviousName.get(node.tool);
    if (!tool) continue;
    node.tool = tool.name;
    node.parameters = structuredClone(tool.input_ports);
    if (node.type === 'remote_sync_tool') node.outputs = structuredClone(tool.output_ports);
  }
}

elements.metadataButton.addEventListener('click', () => {
  renderMetadataDialog();
  elements.metadataDialog.showModal();
});

elements.clearButton.addEventListener('click', () => {
  if (hasUnsavedChanges && !window.confirm('清空会覆盖当前未保存的 Workflow，确定继续吗？')) return;
  if (!resetWorkflow()) return;
  inspector.setWorkflowNodes([]);
  inspector.setRemoteToolReferences([]);
  hasUnsavedChanges = true;
  elements.workflowNameDisplay.textContent = state.name;
  renderWorkflow();
  elements.workflowState.textContent = '已清空';
  elements.workflowState.classList.remove('saved');
});

elements.addCallableWorkflowButton.addEventListener('click', () => {
  elements.callableWorkflowList.querySelector('.metadata-empty')?.remove();
  const row = createCallableWorkflowRow();
  elements.callableWorkflowList.append(row);
  row.querySelector('input').focus();
});

elements.addRemoteToolButton.addEventListener('click', () => {
  elements.remoteToolList.querySelector('.metadata-empty')?.remove();
  const row = createRemoteToolRow();
  elements.remoteToolList.append(row);
  row.querySelector('input').focus();
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

elements.addStructButton.addEventListener('click', addStructDefinition);

elements.metadataForm.addEventListener('submit', (event) => {
  if (event.submitter?.value === 'cancel') return;
  event.preventDefault();
  if (!elements.metadataForm.reportValidity()) return;
  let structs;
  try {
    structs = validateStructDefinitions(structDraft);
    elements.structDefinitionsError.textContent = '';
  } catch (error) {
    elements.structDefinitionsError.textContent = error.message;
    return;
  }
  const inputPorts = readMetadataPorts('input_ports');
  const outputPorts = readMetadataPorts('output_ports');
  const callableWorkflows = readCallableWorkflows();
  const remoteTools = readRemoteTools();
  const allPortLists = [inputPorts, outputPorts, ...callableWorkflows.flatMap((workflow) => [workflow.input_ports, workflow.output_ports]), ...remoteTools.flatMap((tool) => [tool.input_ports, tool.output_ports])];
  if (allPortLists.some((ports) => new Set(ports.map((port) => port.name.toLocaleLowerCase())).size !== ports.length)) {
    elements.resourceState.textContent = '同一侧接口名称不能重复';
    return;
  }
  if (new Set(callableWorkflows.map((workflow) => workflow.name.toLocaleLowerCase())).size !== callableWorkflows.length) {
    elements.resourceState.textContent = '可调用 Workflow 名称不能重复';
    return;
  }
  if (new Set(remoteTools.map((tool) => tool.name.toLocaleLowerCase())).size !== remoteTools.length) {
    elements.resourceState.textContent = 'Remote Tool 名称不能重复';
    return;
  }
  const retainedNames = new Set(callableWorkflows.map((workflow) => workflow.previous_name || workflow.name));
  const removedInUse = state.nodes.find((node) => node.type === 'workflow' && !retainedNames.has(node.workflow_name));
  if (removedInUse) {
    elements.resourceState.textContent = `“${removedInUse.workflow_name}”仍被画布节点调用`;
    return;
  }
  const retainedToolNames = new Set(remoteTools.map((tool) => tool.previous_name || tool.name));
  const removedToolInUse = state.nodes.find((node) => ['remote_sync_tool', 'remote_async_tool'].includes(node.type) && node.tool && !retainedToolNames.has(node.tool));
  if (removedToolInUse) {
    elements.resourceState.textContent = `“${removedToolInUse.tool}”仍被画布节点调用`;
    return;
  }
  const previousSnapshot = workflowSnapshot();
  syncCallableWorkflowNodes(callableWorkflows);
  syncRemoteToolNodes(remoteTools);
  state.name = elements.workflowName.value.trim();
  state.description = elements.workflowDescription.value.trim();
  state.metadata = { ...(state.metadata || {}), structs };
  state.input_ports = inputPorts;
  state.output_ports = outputPorts;
  state.workflow_nodes = callableWorkflows.map(({ previous_name, ...workflow }) => workflow);
  state.remote_tools = remoteTools.map(({ previous_name, ...tool }) => tool);
  const snapshot = workflowSnapshot();
  if (!loadSnapshot(snapshot)) {
    loadSnapshot(previousSnapshot);
    elements.structDefinitionsError.textContent = 'Struct 修改与当前节点或连接不兼容';
    return;
  }
  const retainedConnectionIds = new Set(state.connections.map((connection) => connection.id));
  const removedConnections = previousSnapshot.connections.filter((connection) => !retainedConnectionIds.has(connection.id));
  if (removedConnections.length && !window.confirm(`Struct 修改会删除 ${removedConnections.length} 条不再匹配的连线，继续吗？`)) {
    loadSnapshot(previousSnapshot);
    return;
  }
  inspector.setWorkflowNodes(workflowReferences());
  inspector.setRemoteToolReferences(remoteToolReferences());
  markChanged();
  elements.workflowNameDisplay.textContent = state.name;
  renderWorkflow();
  elements.metadataDialog.close();
});

document.querySelector('#workflowNodeLibrary').addEventListener('click', (event) => {
  const button = event.target.closest('[data-add-workflow-node]');
  if (!button) return;
  const reference = workflowReferences().find((workflow) => workflow.name === button.dataset.addWorkflowNode);
  if (!reference) return;
  const node = addNode('workflow', reference, currentCanvasViewport());
  if (!node) return;
  markChanged();
  editor.selectNode(node.id);
});

for (const button of document.querySelectorAll('[data-add-node]')) {
  button.addEventListener('click', () => {
    const nodeType = button.dataset.addNode;
    placeNode(nodeType);
  });
}

function placeNode(nodeType) {
  const node = addNode(nodeType, {
    output_ports: state.output_ports,
  }, currentCanvasViewport());
  if (!node) return;
  markChanged();
  editor.selectNode(node.id);
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
    importWorkflowText(await file.text());
  } catch (error) {
    elements.workflowState.textContent = error.message || '导入失败';
    elements.workflowState.classList.remove('saved');
  }
});

elements.textImportButton.addEventListener('click', async () => {
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
});

elements.overwriteTextImportButton.addEventListener('click', () => {
  try {
    importWorkflowText(elements.textImportValue.value, '已从文本导入');
    elements.textImportDialog.close();
  } catch (error) {
    elements.textImportError.textContent = error.message || 'Workflow 文本无效';
  }
});

elements.openTextImportButton.addEventListener('click', () => {
  try {
    parseWorkflowText(elements.textImportValue.value);
    const target = new URL('/workflow_edit.html', window.location.origin);
    target.searchParams.set('workflow', elements.textImportValue.value);
    const editorWindow = window.open(target.toString(), '_blank');
    if (!editorWindow) throw new Error('新窗口被浏览器拦截');
    editorWindow.opener = null;
    elements.textImportDialog.close();
  } catch (error) {
    elements.textImportError.textContent = error.message || 'Workflow 文本无效';
  }
});

elements.closeTextImportButton.addEventListener('click', () => elements.textImportDialog.close());
elements.cancelTextImportButton.addEventListener('click', () => elements.textImportDialog.close());

document.addEventListener('paste', (event) => {
  if (!isPristineEditor() || event.target.closest('input, textarea, [contenteditable="true"]')) return;
  const text = event.clipboardData?.getData('text/plain');
  if (!text) return;
  try {
    importWorkflowText(text, '已从剪贴板导入');
    event.preventDefault();
  } catch (error) {
    elements.workflowState.textContent = error.message || '剪贴板导入失败';
  }
});

async function importInitialWorkflow() {
  const workflowParameter = new URLSearchParams(window.location.search).get('workflow');
  if (workflowParameter) {
    try {
      importWorkflowText(workflowParameter, '已从 URL 导入');
    } catch (error) {
      elements.workflowState.textContent = error.message || 'URL Workflow 导入失败';
    }
    return;
  }
  if (!isPristineEditor() || !navigator.clipboard?.readText) return;
  try {
    const text = await navigator.clipboard.readText();
    if (text && isPristineEditor()) importWorkflowText(text, '已从剪贴板自动导入');
  } catch (error) {
    if (error.name !== 'NotAllowedError') console.warn('剪贴板自动导入失败', error);
  }
}

elements.copyButton.addEventListener('click', async () => {
  try {
    await writeClipboardText(JSON.stringify(workflowSnapshot()));
    elements.workflowState.textContent = '已复制到剪贴板';
  } catch (error) {
    elements.workflowState.textContent = error.message || '复制失败';
    elements.workflowState.classList.remove('saved');
  }
});

elements.exportButton.addEventListener('click', () => {
  const snapshot = workflowSnapshot();
  const blob = new Blob([`${JSON.stringify(snapshot, null, 2)}\n`], { type: 'application/json;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  const filename = state.name.replace(/[<>:"/\\|?*]+/g, '-').replace(/\s+/g, '-');
  link.download = `${filename}-${new Date().toISOString().slice(0, 10)}.json`;
  link.click();
  URL.revokeObjectURL(url);
});

window.addEventListener('beforeunload', (event) => {
  if (!hasUnsavedChanges) return;
  event.preventDefault();
  event.returnValue = '';
});

window.addEventListener('resize', editor.renderConnections);

renderWorkflow();
importInitialWorkflow();
