import { portsForNode } from '../domain/node-contract.js';
import { reconcileConnections } from '../domain/connection-rules.js';
import { nodeById, state } from '../domain/serialization.js';
import { createIntegrationInspector } from './integrations.js';
import { bindStructureInspector } from './structure.js';
import { setRuntimeStyles } from '../domain/runtime-styles.js';
import { bindNodeFunctions } from '../domain/functions.js';

export function createInspector(elements, editor, markChanged) {
  const context = { elements, editor, markChanged, renderInspector, renderInterfaceContract };
  const integrations = createIntegrationInspector(context);

  function renderInspector() {
    editor.ensureSelection();
    const node = nodeById(editor.editorState.selectedId) || state.nodes[0];
    if (!node) return;
    editor.editorState.selectedId = node.id;
    elements.inspectorTitle.textContent = node.name;
    elements.inspectorType.textContent = node.type.toUpperCase();
    const template = document.querySelector(`#${node.type}InspectorTemplate`);
    elements.inspectorContent.replaceChildren(template.content.cloneNode(true));
    const functions = state.metadata.functions || [];
    if (['function_input', 'function_output'].includes(node.type)) {
      const section = document.createElement('section');
      section.className = 'inspector-section form-section';
      const label = document.createElement('label');
      label.textContent = '函数';
      const select = document.createElement('select');
      for (const fn of functions) select.add(new Option(fn.name, fn.id));
      select.value = node.function_id || '';
      select.disabled = true;
      label.append(select);
      section.append(label);
      elements.inspectorContent.prepend(section);
    }
    const target = elements.inspectorContent.querySelector('[data-function-target]');
    if (target) {
      target.replaceChildren(...functions.map((fn) => new Option(fn.name, fn.id)));
      target.value = node.callee_id;
      target.addEventListener('change', () => {
        node.callee_id = target.value;
        bindNodeFunctions(state.nodes, functions);
        reconcileConnections(state);
        markChanged();
        editor.renderWorkflow();
      });
    }
    if (node.type === 'input') {
      renderInterfaceContract(node);
      return;
    }
    integrations.prepare(node);
    renderInterfaceContract(node);
    for (const field of elements.inspectorContent.querySelectorAll('[data-field]')) {
      if (node.type === 'list_get' && ['index_source', 'index'].includes(field.dataset.field)) continue;
      field.value = node[field.dataset.field] || '';
      field.addEventListener('input', () => {
        node[field.dataset.field] = field.value;
        markChanged();
        editor.renderNodes();
        elements.inspectorTitle.textContent = node.name;
      });
    }
    bindStructureInspector(node, context);
    integrations.bind(node);
    if (node.type === 'construct_message') {
      const roleFields = elements.inspectorContent.querySelectorAll('[data-role-source]');
      const roleSelect = elements.inspectorContent.querySelector('[data-field="role"]');
      const updateRoleSource = () => {
        roleSelect.hidden = node.role_source === 'port';
        roleSelect.closest('label').hidden = node.role_source === 'port';
      };
      for (const field of roleFields) {
        field.checked = field.value === node.role_source;
        field.addEventListener('change', () => {
          if (!field.checked) return;
          node.role_source = field.value;
          reconcileConnections(state);
          markChanged();
          editor.renderNodes();
          renderInspector();
        });
      }
      updateRoleSource();
    }
    elements.inspectorContent.querySelector('[data-delete-node]')?.addEventListener('click', () => {
      editor.deleteSelectedNode();
    });
  }

  function renderInterfaceContract(node) {
    const mount = elements.inspectorContent.querySelector('[data-interface-contract]');
    if (!mount) return;
    const component = document.querySelector('#interfaceContractTemplate').content.firstElementChild.cloneNode(true);
    component.querySelector('.section-label strong').textContent = mount.dataset.contractTitle || '接口契约';
    component.querySelector('[data-contract-status]').textContent = mount.dataset.contractStatus || '只读';
    const ports = portsForNode(node);
    const renderPorts = (direction, selector, emptyText) => {
      const portElements = ports.filter((port) => port.direction === direction).map((port) => {
        const contract = document.querySelector('#portContractTemplate').content.firstElementChild.cloneNode(true);
        contract.querySelector('.port-swatch').classList.add(port.type);
        if (port.color) setRuntimeStyles(contract.querySelector('.port-swatch'), `inspector-port:${node.id}:${port.direction}:${port.id}`, { 'background-color': port.color });
        contract.querySelector('strong').textContent = port.label;
        contract.querySelector('code').textContent = port.contract || port.type;
        contract.title = port.title;
        return contract;
      });
      if (!portElements.length) portElements.push(Object.assign(document.createElement('div'), { className: 'empty-options', textContent: emptyText }));
      component.querySelector(selector).replaceChildren(...portElements);
    };
    renderPorts('input', '[data-contract-inputs]', '无输入接口');
    renderPorts('output', '[data-contract-outputs]', '无输出接口');
    mount.replaceChildren(component);
  }

  function setSubprocessWorkflowFiles(references) {
    const workflowNodes = references.filter((reference) => typeof reference.name === 'string' && reference.name);
    elements.subprocessNodeLibrary.hidden = workflowNodes.length === 0;
    elements.subprocessNodeLibrary.replaceChildren(...workflowNodes.map((reference) => {
      const button = document.createElement('button');
      button.className = 'library-item subprocess-library-item';
      button.type = 'button';
      button.dataset.addSubprocessNode = reference.name;
      button.innerHTML = '<span class="node-symbol spawn_and_wait_subprocess-symbol" aria-hidden="true">WF</span><div><strong></strong><small></small></div><span class="add-symbol" aria-hidden="true">+</span>';
      button.querySelector('strong').textContent = '拉起并等待子进程';
      button.querySelector('small').textContent = `${(reference.input_ports || []).length} 输入 / ${(reference.output_ports || []).length} 输出`;
      return button;
    }));
  }

  function setRemoteToolReferences(references) {
    integrations.setRemoteToolReferences(references);
  }

  editor.setInspectorRenderer(renderInspector);
  return {
    renderInspector,
    setModels: integrations.setModels,
    setLocalTools: integrations.setLocalTools,
    setMetadataTools: integrations.setMetadataTools,
    setRemoteToolReferences,
    setRemoteToolSchemas: integrations.setRemoteToolSchemas,
    setSubprocessWorkflowFiles,
  };
}
