import { createWorkflowId, deleteNode, nodeById, state } from './model.js';

export function createWorkflowView(elements, connections, markChanged) {
  const portRowHeight = 28;
  const portTopInset = 8;
  let modelConfigs = [];
  let toolSchemas = [];

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
        { id: 'content-in', direction: 'input', type: 'content', label: '输入', title: '输入内容', multiple: false },
        ...node.branches.map((branch) => ({ id: branch.id, direction: 'output', type: 'control', label: branch.name, title: branch.name, multiple: false })),
      ];
    }
    if (node.type === 'construct_message') {
      return [
        { id: 'control-in', direction: 'input', type: 'control', label: '触发', title: '触发', multiple: false },
        { id: 'content-in', direction: 'input', type: 'content', label: 'Content', title: 'Message content', multiple: false },
        { id: 'control-out', direction: 'output', type: 'control', label: '下一步', title: '下一步', multiple: false },
        { id: 'message-out', direction: 'output', type: 'message', label: 'Message', title: '构造后的 Message', multiple: true },
      ];
    }
    if (node.type === 'construct_content') {
      return [
        { id: 'control-in', direction: 'input', type: 'control', label: '触发', title: '触发', multiple: false },
        { id: 'control-out', direction: 'output', type: 'control', label: '下一步', title: '下一步', multiple: false },
        { id: 'content-out', direction: 'output', type: 'content', label: 'Content', title: '构造后的 Content', multiple: true },
      ];
    }
    if (node.type === 'construct_list') {
      const itemPorts = (node.dataInputPorts || []).map((portId, index) => ({
        id: portId,
        direction: 'input',
        type: node.item_type,
        label: `${node.item_type} ${index}`,
        title: `列表初始值 ${index}`,
        multiple: false,
      }));
      return [
        { id: 'control-in', direction: 'input', type: 'control', label: '触发', title: '触发', multiple: false },
        ...itemPorts,
        { id: 'control-out', direction: 'output', type: 'control', label: '下一步', title: '下一步', multiple: false },
        { id: 'list-out', direction: 'output', type: `list-${node.item_type}`, label: '列表', title: `list-${node.item_type}`, multiple: true },
      ];
    }
    if (node.type === 'tool') {
      const parameterPorts = (node.parameters || []).map((parameter) => ({
        id: parameter,
        direction: 'input',
        type: 'content',
        label: parameter,
        title: `工具参数: ${parameter}`,
        multiple: false,
      }));
      return [
        { id: 'control-in', direction: 'input', type: 'control', label: '触发', title: '触发', multiple: false },
        ...parameterPorts,
        { id: 'control-out', direction: 'output', type: 'control', label: '下一步', title: '下一步', multiple: false },
        { id: 'output', direction: 'output', type: 'content', label: '结果', title: '工具执行结果', multiple: true },
      ];
    }
    if (node.type === 'tool_calls') {
      return [
        { id: 'control-in', direction: 'input', type: 'control', label: '触发', title: '触发', multiple: false },
        { id: 'tool_calls', direction: 'input', type: 'content', label: 'Tool Calls JSON', title: 'OpenAI 格式的 tool_calls JSON', multiple: false },
        { id: 'control-out', direction: 'output', type: 'control', label: '下一步', title: '下一步', multiple: false },
        { id: 'output', direction: 'output', type: 'content', label: '结果', title: 'Tool Calls 执行结果', multiple: true },
      ];
    }
    const inputPorts = (node.dataInputPorts || ['message-in-0']).map((portId, index) => ({
      id: portId,
      direction: 'input',
      type: 'message',
      label: `Message ${index}`,
      title: `Message ${index}`,
      multiple: false,
    }));
    const ports = [
      { id: 'control-in', direction: 'input', type: 'control', label: '触发', title: '触发', multiple: false },
      ...inputPorts,
      { id: 'control-out', direction: 'output', type: 'control', label: '下一步', title: '下一步', multiple: false },
      { id: 'output', direction: 'output', type: 'content', label: '输出', title: '模型输出', multiple: true },
    ];
    if (node.think === true) ports.push({ id: 'reasoning', direction: 'output', type: 'content', label: '思考', title: '推理过程', multiple: true });
    if (node.tool_calls === true) ports.push({ id: 'tool_calls', direction: 'output', type: 'content', label: 'Tool Calls', title: 'OpenAI 格式的 tool_calls JSON', multiple: true });
    return ports;
  }

  function createNodeUI(node) {
    const element = document.createElement('button');
    const ports = nodePorts(node);
    const inputs = ports.filter((port) => port.direction === 'input');
    const outputs = ports.filter((port) => port.direction === 'output');
    const bodyRows = Math.max(inputs.length, outputs.length);
    const symbol = node.type === 'input' ? 'IN' : node.type === 'router' ? 'R' : node.type === 'construct_message' ? 'M' : node.type === 'construct_content' ? 'C' : node.type === 'construct_list' ? 'L' : node.type === 'tool' ? 'T' : node.type === 'tool_calls' ? 'TC' : 'L';

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

    if (node.type === 'llm') renderModelOptions(node);
    if (node.type === 'tool') renderToolSelect(node);
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
    if (node.type === 'construct_list') bindConstructList(node);
    if (node.type === 'llm') bindLlm(node);
    elements.inspectorContent.querySelector('[data-delete-node]').addEventListener('click', () => {
      deleteNode(node.id);
      markChanged();
      renderNodes();
      renderInspector();
    });
  }

  function bindConstructList(node) {
    const contracts = elements.inspectorContent.querySelector('[data-list-input-contracts]');
    const outputType = elements.inspectorContent.querySelector('[data-list-output-type]');
    const outputSwatch = elements.inspectorContent.querySelector('[data-list-output-swatch]');
    outputType.textContent = `list-${node.item_type}`;
    outputSwatch.classList.add(`list-${node.item_type}`);
    contracts.replaceChildren(...node.dataInputPorts.map((portId, index) => {
      const contract = document.createElement('div');
      contract.className = 'port-contract';
      contract.innerHTML = '<span class="port-swatch"></span><strong></strong><code></code>';
      contract.querySelector('.port-swatch').classList.add(node.item_type);
      contract.querySelector('strong').textContent = `${node.item_type} ${index}`;
      contract.querySelector('code').textContent = node.item_type;
      return contract;
    }));
    const typeField = elements.inspectorContent.querySelector('[data-field="item_type"]');
    const countField = elements.inspectorContent.querySelector('[data-field="initial_value_count"]');
    typeField.value = node.item_type;
    countField.value = node.initial_value_count;
    typeField.addEventListener('change', () => {
      node.item_type = typeField.value;
      node.dataInputPorts = node.dataInputPorts.map((_, index) => `${node.item_type}-in-${index}`);
      state.connections = state.connections.filter((connection) => connection.fromId !== node.id && connection.toId !== node.id);
      markChanged();
      renderNodes();
      renderInspector();
    });
    countField.addEventListener('change', () => {
      node.initial_value_count = Math.min(20, Math.max(0, Number.parseInt(countField.value, 10) || 0));
      node.dataInputPorts = Array.from({ length: node.initial_value_count }, (_, index) => `${node.item_type}-in-${index}`);
      state.connections = state.connections.filter((connection) => !(connection.toId === node.id && !node.dataInputPorts.includes(connection.toPortId)));
      markChanged();
      renderNodes();
      renderInspector();
    });
  }

  function renderModelOptions(node) {
    const select = elements.inspectorContent.querySelector('[data-field="model"]');
    const legacyMatches = modelConfigs.filter((model) => model.model === node.model || model.name === node.model);
    if (!modelConfigs.some((model) => model.id === node.model) && legacyMatches.length === 1) {
      node.model = legacyMatches[0].id;
      markChanged();
    }
    if (!node.model && modelConfigs.length) {
      node.model = modelConfigs[0].id;
      markChanged();
    }

    const options = modelConfigs.map((model) => {
      const option = document.createElement('option');
      option.value = model.id;
      option.textContent = model.name;
      return option;
    });
    if (!modelConfigs.some((model) => model.id === node.model)) {
      const unavailable = document.createElement('option');
      unavailable.value = node.model || '';
      unavailable.textContent = node.model ? `当前不可用 (${node.model})` : '没有可用的模型配置';
      options.unshift(unavailable);
    }
    select.replaceChildren(...options);
    select.disabled = modelConfigs.length === 0;
  }

  function renderBranches(node) {
    const container = elements.inspectorContent.querySelector('[data-route-options]');
    const contract = elements.inspectorContent.querySelector('[data-router-output-contracts]');
    node.branches.forEach((branch, index) => {
      const portContract = document.createElement('div');
      portContract.className = 'port-contract';
      portContract.innerHTML = '<span class="port-swatch control"></span><strong></strong><code>control</code>';
      portContract.querySelector('strong').textContent = branch.name;
      contract.append(portContract);

      const option = document.createElement('div');
      option.className = 'route-option';
      option.innerHTML = '<span class="route-index"></span><label><input data-branch-name maxlength="30"><small>控制流输出分支</small></label><button type="button" class="branch-delete" data-delete-branch title="删除分支">×</button>';
      option.querySelector('.route-index').textContent = String(index + 1).padStart(2, '0');
      const input = option.querySelector('[data-branch-name]');
      input.value = branch.name;
      input.addEventListener('input', () => {
        branch.name = input.value || `分支 ${index + 1}`;
        portContract.querySelector('strong').textContent = branch.name;
        markChanged();
        renderNodes();
      });
      option.querySelector('[data-delete-branch]').addEventListener('click', () => {
        if (node.branches.length <= 1) return;
        const removed = node.branches.splice(index, 1)[0];
        state.connections = state.connections.filter((connection) => !(connection.fromId === node.id && connection.fromPortId === removed.id));
        markChanged();
        renderNodes();
        renderInspector();
      });
      container.append(option);
    });
    elements.inspectorContent.querySelector('[data-add-branch]').addEventListener('click', () => {
      const id = createWorkflowId('branch');
      node.branches.push({ id, name: `分支 ${node.branches.length + 1}` });
      markChanged();
      renderNodes();
      renderInspector();
    });
  }

  function renderToolSelect(node) {
    const select = elements.inspectorContent.querySelector('[data-field="tool"]');
    const selectedSchema = toolSchemas.find((tool) => tool.name === node.tool);
    if (selectedSchema) {
      node.parameters = Object.keys(selectedSchema.parameters?.properties || {});
    }
    if (!node.tool && toolSchemas.length) {
      node.tool = toolSchemas[0].name;
      node.parameters = Object.keys(toolSchemas[0].parameters?.properties || {});
      markChanged();
    }
    const options = toolSchemas.map((tool) => {
      const option = document.createElement('option');
      option.value = tool.name;
      option.textContent = tool.name;
      option.title = tool.description || '';
      return option;
    });
    if (!toolSchemas.some((tool) => tool.name === node.tool)) {
      const unavailable = document.createElement('option');
      unavailable.value = node.tool || '';
      unavailable.textContent = node.tool ? `当前未注册 (${node.tool})` : '没有已注册的 Tool';
      options.unshift(unavailable);
    }
    select.replaceChildren(...options);
    select.disabled = toolSchemas.length === 0;
    renderToolInputContracts(node);
    select.addEventListener('change', () => {
      const schema = toolSchemas.find((tool) => tool.name === select.value);
      node.tool = select.value;
      node.parameters = Object.keys(schema?.parameters?.properties || {});
      state.connections = state.connections.filter((connection) => {
        if (connection.toId === node.id) return false;
        if (connection.fromId === node.id) return ['control-out', 'output'].includes(connection.fromPortId);
        return true;
      });
      markChanged();
      renderNodes();
      renderInspector();
    });
  }

  function renderToolInputContracts(node) {
    const container = elements.inspectorContent.querySelector('[data-tool-input-contracts]');
    const parameters = node.parameters || [];
    if (!parameters.length) {
      container.replaceChildren(Object.assign(document.createElement('div'), {
        className: 'empty-options',
        textContent: '该 Tool 没有参数',
      }));
      return;
    }
    container.replaceChildren(...parameters.map((parameter) => {
      const contract = document.createElement('div');
      contract.className = 'port-contract';
      contract.innerHTML = '<span class="port-swatch content"></span><strong></strong><code>content</code>';
      contract.querySelector('strong').textContent = parameter;
      return contract;
    }));
  }

  function bindTools(node) {
    const count = elements.inspectorContent.querySelector('[data-tool-count]');
    const container = elements.inspectorContent.querySelector('.tool-options');
    const availableNames = new Set(toolSchemas.map((tool) => tool.name));
    const unavailableTools = node.tools.filter((toolName) => !availableNames.has(toolName));
    const options = toolSchemas.map((tool) => {
      const label = document.createElement('label');
      label.innerHTML = '<input type="checkbox" data-tool><span><strong></strong><small></small></span>';
      const input = label.querySelector('input');
      input.value = tool.name;
      label.querySelector('strong').textContent = tool.name;
      label.querySelector('small').textContent = tool.description || '无描述';
      return label;
    });
    for (const toolName of unavailableTools) {
      const label = document.createElement('label');
      label.innerHTML = '<input type="checkbox" data-tool disabled><span><strong></strong><small>当前未注册</small></span>';
      label.querySelector('input').value = toolName;
      label.querySelector('input').checked = true;
      label.querySelector('strong').textContent = toolName;
      options.push(label);
    }
    if (!options.length) {
      const empty = document.createElement('div');
      empty.className = 'empty-options';
      empty.textContent = '没有已注册的 Tool';
      options.push(empty);
    }
    container.replaceChildren(...options);
    const inputs = elements.inspectorContent.querySelectorAll('[data-tool]');
    function syncCount() { count.textContent = `${node.tools.length} 个`; }
    for (const input of inputs) {
      input.checked = node.tools.includes(input.value);
      input.addEventListener('change', () => {
        node.tools = [...unavailableTools, ...Array.from(inputs).filter((item) => item.checked && !item.disabled).map((item) => item.value)];
        syncCount();
        markChanged();
        renderNodes();
      });
    }
    syncCount();
  }

  function bindLlm(node) {
    renderLlmInputs(node);
    renderLlmOutputContracts(node);
    const toolsSection = elements.inspectorContent.querySelector('[data-llm-tools]');
    const think = elements.inspectorContent.querySelector('[data-think]');
    const toolCalls = elements.inspectorContent.querySelector('[data-tool-calls]');
    if (node.tool_calls === true) bindTools(node);
    else toolsSection.remove();
    think.checked = node.think === true;
    toolCalls.checked = node.tool_calls === true;
    think.addEventListener('change', () => {
      node.think = think.checked;
      if (!node.think) {
        state.connections = state.connections.filter((connection) => !(connection.fromId === node.id && connection.fromPortId === 'reasoning'));
      }
      markChanged();
      renderNodes();
      renderInspector();
    });
    toolCalls.addEventListener('change', () => {
      node.tool_calls = toolCalls.checked;
      if (!node.tool_calls) {
        node.tools = [];
        state.connections = state.connections.filter((connection) => !(connection.fromId === node.id && connection.fromPortId === 'tool_calls'));
      }
      markChanged();
      renderNodes();
      renderInspector();
    });
  }

  function renderLlmInputs(node) {
    const options = elements.inspectorContent.querySelector('[data-llm-input-options]');
    const contracts = elements.inspectorContent.querySelector('[data-llm-input-contracts]');
    node.dataInputPorts.forEach((portId, index) => {
      const contract = document.createElement('div');
      contract.className = 'port-contract';
      contract.innerHTML = '<span class="port-swatch message"></span><strong></strong><code>message</code>';
      contract.querySelector('strong').textContent = `Message ${index}`;
      contracts.append(contract);

      const option = document.createElement('div');
      option.className = 'route-option';
      option.innerHTML = '<span class="route-index"></span><label><strong></strong><small></small></label><button type="button" class="branch-delete" data-delete-input title="删除最后一个输入">×</button>';
      option.querySelector('.route-index').textContent = String(index).padStart(2, '0');
      option.querySelector('strong').textContent = `Message ${index}`;
      option.querySelector('small').textContent = portId;
      option.querySelector('[data-delete-input]').addEventListener('click', () => {
        if (node.dataInputPorts.length <= 1 || index !== node.dataInputPorts.length - 1) return;
        state.connections = state.connections.filter((connection) => !(connection.toId === node.id && connection.toPortId === portId));
        node.dataInputPorts.pop();
        markChanged();
        renderNodes();
        renderInspector();
      });
      options.append(option);
    });
    elements.inspectorContent.querySelector('[data-add-llm-input]').addEventListener('click', () => {
      if (node.dataInputPorts.length >= 20) return;
      node.dataInputPorts.push(`message-in-${node.dataInputPorts.length}`);
      markChanged();
      renderNodes();
      renderInspector();
    });
  }

  function renderLlmOutputContracts(node) {
    const contract = elements.inspectorContent.querySelector('[data-llm-output-contracts]');
    const outputs = [
      { label: '下一步', type: 'control' },
      { label: '输出', type: 'content' },
    ];
    if (node.think === true) outputs.push({ label: '思考', type: 'content' });
    if (node.tool_calls === true) outputs.push({ label: 'Tool Calls', type: 'content' });
    contract.replaceChildren(...outputs.map((output) => {
      const portContract = document.createElement('div');
      portContract.className = 'port-contract';
      portContract.innerHTML = '<span class="port-swatch"></span><strong></strong><code></code>';
      portContract.querySelector('.port-swatch').classList.add(output.type);
      portContract.querySelector('strong').textContent = output.label;
      portContract.querySelector('code').textContent = output.type;
      return portContract;
    }));
  }

  function setModels(models) {
    modelConfigs = models.filter((model) => model.enabled === true);
    if (nodeById(state.selectedId)?.type === 'llm') renderInspector();
  }

  function setTools(tools) {
    toolSchemas = tools.filter((tool) => typeof tool.name === 'string' && tool.name);
    if (['llm', 'tool'].includes(nodeById(state.selectedId)?.type)) renderInspector();
  }

  return { renderInspector, renderNodes, setModels, setTools };
}