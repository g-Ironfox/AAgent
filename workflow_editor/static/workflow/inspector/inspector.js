import { portsForNode } from '../domain/node-contract.js';
import { deleteNode, nodeById, state } from '../domain/serialization.js';
import { createIntegrationInspector } from './integrations.js';
import { bindStructureInspector } from './structure.js';

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
    if (node.type === 'input') {
      renderInterfaceContract(node);
      return;
    }
    integrations.prepare(node);
    renderInterfaceContract(node);
    for (const field of elements.inspectorContent.querySelectorAll('[data-field]')) {
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
    elements.inspectorContent.querySelector('[data-delete-node]')?.addEventListener('click', () => {
      deleteNode(node.id);
      editor.ensureSelection();
      markChanged();
      editor.renderNodes();
      renderInspector();
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

  function setWorkflowNodes(references) {
    const workflowNodes = references.filter((reference) => typeof reference.name === 'string' && reference.name);
    elements.workflowNodeLibrary.hidden = workflowNodes.length === 0;
    elements.workflowNodeLibrary.replaceChildren(...workflowNodes.map((reference) => {
      const button = document.createElement('button');
      button.className = 'library-item workflow-library-item';
      button.type = 'button';
      button.dataset.addWorkflowNode = reference.name;
      button.innerHTML = '<span class="node-symbol workflow-symbol" aria-hidden="true">WF</span><div><strong></strong><small></small></div><span class="add-symbol" aria-hidden="true">+</span>';
      button.querySelector('strong').textContent = reference.name;
      button.querySelector('small').textContent = `${(reference.input_ports || []).length} 输入 / ${(reference.output_ports || []).length} 输出`;
      return button;
    }));
  }

  editor.setInspectorRenderer(renderInspector);
  return { renderInspector, setModels: integrations.setModels, setTools: integrations.setTools, setWorkflowNodes };
}