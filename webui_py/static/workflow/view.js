import { deleteNode, nodeById, state } from './model.js';

export function createWorkflowView(elements, connections, markChanged) {
  const portRowHeight = 28;
  const portTopInset = 8;

  function nodePorts(node) {
    if (node.type === 'input') {
      return [
        { id: 'control-out', direction: 'output', type: 'control', label: '下一步', title: '下一步', multiple: false },
        { id: 'content-out', direction: 'output', type: 'content', label: '输入内容', title: '输入内容', multiple: true },
      ];
    }
    if (node.type === 'router') {
      return [
        { id: 'control-in', direction: 'input', type: 'control', label: '触发', title: '触发', multiple: false },
        ...node.branches.map((branch) => ({ id: branch.id, direction: 'output', type: 'control', label: branch.name, title: branch.name, multiple: false })),
      ];
    }
    return [
      { id: 'control-in', direction: 'input', type: 'control', label: '触发', title: '触发', multiple: false },
      { id: 'content-in', direction: 'input', type: 'content', label: '上下文', title: '上下文', multiple: false },
      { id: 'control-out', direction: 'output', type: 'control', label: '下一步', title: '下一步', multiple: false },
    ];
  }

  function createNodeUI(node) {
    const element = document.createElement('button');
    const ports = nodePorts(node);
    const inputs = ports.filter((port) => port.direction === 'input');
    const outputs = ports.filter((port) => port.direction === 'output');
    const bodyRows = Math.max(inputs.length, outputs.length);
    const symbol = node.type === 'input' ? 'IN' : node.type === 'router' ? 'R' : 'L';

    element.type = 'button';
    element.className = `flow-node ${node.type}${node.id === state.selectedId ? ' selected' : ''}`;
    element.style.left = `${node.x}px`;
    element.style.top = `${node.y}px`;
    element.dataset.nodeId = node.id;

    const head = document.createElement('span');
    head.className = 'flow-node-head';
    head.innerHTML = `<span class="node-symbol ${node.type}-symbol">${symbol}</span><span><strong></strong><small></small></span>`;
    head.querySelector('strong').textContent = node.name;
    head.querySelector('small').textContent = node.type.toUpperCase();

    const body = document.createElement('span');
    body.className = 'flow-node-body';
    body.style.height = `${Math.max(70, portTopInset + bodyRows * portRowHeight)}px`;
    for (const port of ports) {
      const portElement = document.createElement('span');
      const row = port.direction === 'input' ? inputs.indexOf(port) : outputs.indexOf(port);
      portElement.className = 'node-port';
      portElement.style.top = `${portTopInset + row * portRowHeight}px`;
      portElement.dataset.portId = port.id;
      portElement.dataset.portDirection = port.direction;
      portElement.dataset.portType = port.type;
      portElement.dataset.portMultiple = String(port.multiple === true);
      portElement.dataset.portLabel = port.label;
      portElement.title = port.title;
      body.append(portElement);
    }

    element.append(head, body);
    element.addEventListener('click', () => selectNode(node.id));
    element.querySelectorAll('.node-port').forEach((port) => connections.bindConnectionPort(port, node));
    connections.bindNodeDrag(element, node);
    return element;
  }

  function renderNodes() {
    const fragment = document.createDocumentFragment();
    for (const node of state.nodes) {
      fragment.append(createNodeUI(node));
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
    if (node.type === 'router') renderBranches(node);
    if (node.type === 'llm') bindTools(node);
    elements.inspectorContent.querySelector('[data-delete-node]').addEventListener('click', () => {
      deleteNode(node.id);
      markChanged();
      renderNodes();
      renderInspector();
    });
  }

  function renderBranches(node) {
    const container = elements.inspectorContent.querySelector('[data-route-options]');
    node.branches.forEach((branch, index) => {
      const option = document.createElement('div');
      option.className = 'route-option';
      option.innerHTML = '<span class="route-index"></span><label><input data-branch-name maxlength="30"><small>控制流输出分支</small></label><button type="button" class="branch-delete" data-delete-branch title="删除分支">×</button>';
      option.querySelector('.route-index').textContent = String(index + 1).padStart(2, '0');
      const input = option.querySelector('[data-branch-name]');
      input.value = branch.name;
      input.addEventListener('input', () => {
        branch.name = input.value || `分支 ${index + 1}`;
        markChanged();
        renderNodes();
      });
      option.querySelector('[data-delete-branch]').addEventListener('click', () => {
        if (node.branches.length <= 1) return;
        const removed = node.branches.splice(index, 1)[0];
        state.connections = state.connections.filter((connection) => connection.fromPortId !== removed.id);
        markChanged();
        renderNodes();
        renderInspector();
      });
      container.append(option);
    });
    elements.inspectorContent.querySelector('[data-add-branch]').addEventListener('click', () => {
      const id = `branch-${Date.now()}`;
      node.branches.push({ id, name: `分支 ${node.branches.length + 1}` });
      markChanged();
      renderNodes();
      renderInspector();
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