import { deleteNode, llmNodes, nodeById, state } from './model.js';

export function createWorkflowView(elements, connections, markChanged) {
  function nodeDescription(node) {
    if (node.type === 'input') return [['输出', 'control + content'], ['来源', '用户输入']];
    if (node.type === 'router') return [['模式', 'LLM 多选一'], ['候选', `${llmNodes().length} 个 LLM`]];
    return [['模型', node.model], ['Tools', `${node.tools.length} 个已挂载`]];
  }

  function renderNodes() {
    const fragment = document.createDocumentFragment();
    for (const node of state.nodes) {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = `flow-node ${node.type}${node.id === state.selectedId ? ' selected' : ''}`;
      button.style.left = `${node.x}px`;
      button.style.top = `${node.y}px`;
      button.dataset.nodeId = node.id;
      button.innerHTML = `
        ${node.type !== 'input' ? '<span class="node-port input" data-port-direction="input" data-port-type="control" title="控制流输入"></span>' : ''}
        ${node.type === 'llm' ? '<span class="node-port text-input" data-port-direction="input" data-port-type="content" title="文本输入"></span>' : ''}
        <span class="node-port output" data-port-direction="output" data-port-type="control" title="控制流输出"></span>
        ${node.type === 'input' ? '<span class="node-port content-output" data-port-direction="output" data-port-type="content" title="文本输出"></span>' : ''}
        <span class="flow-node-header"><span class="node-symbol ${node.type}-symbol">${node.type === 'input' ? 'IN' : node.type === 'router' ? 'R' : 'L'}</span><span><strong></strong><small></small></span></span>
        <span class="flow-node-body"></span>`;
      button.querySelector('.flow-node-header strong').textContent = node.name;
      button.querySelector('.flow-node-header small').textContent = node.type.toUpperCase();
      const body = button.querySelector('.flow-node-body');
      for (const [label, value] of nodeDescription(node)) {
        const detail = document.createElement('span');
        detail.className = 'node-detail';
        detail.innerHTML = '<span></span><strong></strong>';
        detail.querySelector('span').textContent = label;
        detail.querySelector('strong').textContent = value;
        body.append(detail);
      }
      button.addEventListener('click', () => selectNode(node.id));
      button.querySelectorAll('.node-port').forEach((port) => connections.bindConnectionPort(port, node));
      connections.bindNodeDrag(button, node);
      fragment.append(button);
    }
    elements.nodeLayer.replaceChildren(fragment);
    elements.nodeCount.textContent = `${state.nodes.length} 个实例`;
    requestAnimationFrame(connections.renderConnections);
  }

  function selectNode(id) {
    state.selectedId = id;
    renderNodes();
    renderInspector();
  }

  function renderInspector() {
    const node = nodeById(state.selectedId) || state.nodes[0];
    state.selectedId = node.id;
    elements.inspectorTitle.textContent = node.name;
    elements.inspectorType.textContent = node.type.toUpperCase();
    const template = document.querySelector(`#${node.type}InspectorTemplate`);
    elements.inspectorContent.replaceChildren(template.content.cloneNode(true));
    if (node.type === 'input') return;

    for (const field of elements.inspectorContent.querySelectorAll('[data-field]')) {
      field.value = node[field.dataset.field] || '';
      field.addEventListener('input', () => {
        node[field.dataset.field] = field.value;
        markChanged();
        renderNodes();
        elements.inspectorTitle.textContent = node.name;
      });
    }
    if (node.type === 'router') renderRouteOptions();
    if (node.type === 'llm') bindTools(node);
    elements.inspectorContent.querySelector('[data-delete-node]').addEventListener('click', () => {
      deleteNode(node.id);
      markChanged();
      renderNodes();
      renderInspector();
    });
  }

  function renderRouteOptions() {
    const container = elements.inspectorContent.querySelector('[data-route-options]');
    const targets = llmNodes();
    if (!targets.length) {
      const empty = document.createElement('div');
      empty.className = 'empty-options';
      empty.textContent = '添加 LLM 节点后，它会出现在候选分支中';
      container.append(empty);
      return;
    }
    targets.forEach((target, index) => {
      const option = document.createElement('div');
      option.className = 'route-option';
      option.innerHTML = '<span class="route-index"></span><div><strong></strong><small>可由 Router 选择</small></div>';
      option.querySelector('.route-index').textContent = String(index + 1).padStart(2, '0');
      option.querySelector('strong').textContent = target.name;
      container.append(option);
    });
  }

  function bindTools(node) {
    const count = elements.inspectorContent.querySelector('[data-tool-count]');
    const inputs = elements.inspectorContent.querySelectorAll('[data-tool]');
    function syncCount() { count.textContent = `${node.tools.length} 个`; }
    for (const input of inputs) {
      input.checked = node.tools.includes(input.value);
      input.addEventListener('change', () => {
        node.tools = Array.from(inputs).filter((item) => item.checked).map((item) => item.value);
        syncCount();
        markChanged();
        renderNodes();
      });
    }
    syncCount();
  }

  return { renderInspector, renderNodes };
}