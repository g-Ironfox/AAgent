import { reconcileConnections } from '../domain/connection-rules.js';
import { nodeById, state } from '../domain/serialization.js';

export function createIntegrationInspector(context) {
  let modelConfigs = [];
  let localToolSchemas = [];
  let remoteToolReferences = [];

  function prepare(node) {
    if (node.type === 'llm') renderModelOptions(node);
    if (node.type === 'local_tool') renderLocalToolSelect(node);
    if (['remote_sync_tool', 'remote_async_tool'].includes(node.type)) renderRemoteToolFields(node);
    if (node.type === 'workflow') context.elements.inspectorContent.querySelector('[data-workflow-name]').value = node.workflow_name;
  }

  function bind(node) {
    if (node.type === 'llm') bindLlm(node);
    if (['remote_sync_tool', 'remote_async_tool'].includes(node.type)) bindRemoteTool(node);
  }

  function renderModelOptions(node) {
    const select = context.elements.inspectorContent.querySelector('[data-field="model"]');
    const legacyMatches = modelConfigs.filter((model) => model.model === node.model || model.name === node.model);
    if (!modelConfigs.some((model) => model.id === node.model) && legacyMatches.length === 1) {
      node.model = legacyMatches[0].id;
      context.markChanged();
    }
    if (!node.model && modelConfigs.length) {
      node.model = modelConfigs[0].id;
      context.markChanged();
    }
    const options = modelConfigs.map((model) => Object.assign(document.createElement('option'), { value: model.id, textContent: model.name }));
    if (!modelConfigs.some((model) => model.id === node.model)) {
      options.unshift(Object.assign(document.createElement('option'), {
        value: node.model || '',
        textContent: node.model ? `当前不可用 (${node.model})` : '没有可用的模型配置',
      }));
    }
    select.replaceChildren(...options);
    select.disabled = modelConfigs.length === 0;
  }

  function renderLocalToolSelect(node) {
    const select = context.elements.inspectorContent.querySelector('[data-field="tool"]');
    let selectedSchema = localToolSchemas.find((tool) => tool.name === node.tool);
    if (!selectedSchema) {
      selectedSchema = localToolSchemas[0];
      node.tool = selectedSchema?.name || '';
      node.parameters = Object.keys(selectedSchema?.inputSchema?.properties || {});
      context.markChanged();
    } else node.parameters = Object.keys(selectedSchema.inputSchema?.properties || {});
    const options = localToolSchemas.map((tool) => {
      const option = Object.assign(document.createElement('option'), { value: tool.name, textContent: tool.name });
      option.title = tool.description || '';
      return option;
    });
    if (!options.length) options.push(Object.assign(document.createElement('option'), { value: '', textContent: '没有已注册的 Tool' }));
    select.replaceChildren(...options);
    select.disabled = localToolSchemas.length === 0;
    select.addEventListener('change', () => {
      const schema = localToolSchemas.find((tool) => tool.name === select.value);
      node.tool = select.value;
      node.parameters = Object.keys(schema?.inputSchema?.properties || {});
      reconcileConnections(state);
      context.markChanged();
      context.editor.renderNodes();
      context.renderInspector();
    });
  }

  function renderRemoteToolFields(node) {
    renderRemoteToolSelect(node);
    if (node.type === 'remote_async_tool') renderCallback(node);
  }

  function renderRemoteToolSelect(node) {
    const toolSelect = context.elements.inspectorContent.querySelector('[data-field="tool"]');
    const options = remoteToolReferences.map((tool) => Object.assign(document.createElement('option'), { value: tool.name, textContent: tool.name }));
    if (!remoteToolReferences.some((tool) => tool.name === node.tool)) {
      options.unshift(Object.assign(document.createElement('option'), {
        value: '',
        textContent: remoteToolReferences.length ? '选择已注册的 Remote Tool' : '元数据中没有 Remote Tool',
      }));
    }
    toolSelect.replaceChildren(...options);
    toolSelect.disabled = remoteToolReferences.length === 0;
  }

  function renderCallback(node) {
    const enabled = context.elements.inspectorContent.querySelector('[data-callback-enabled]');
    const options = context.elements.inspectorContent.querySelector('[data-callback-options]');
    const callback = node.callback;
    enabled.checked = callback !== null;
    options.hidden = callback === null;
    options.querySelector('[data-callback-queue]').value = callback?.queue || 'main_agent_queue';
    options.querySelector('[data-callback-event-type]').value = callback?.event_type || 'async_result';
    for (const input of options.querySelectorAll('[data-callback-status]')) {
      input.checked = callback?.on?.includes(input.value) ?? ['completed', 'failed'].includes(input.value);
    }
  }

  function bindRemoteTool(node) {
    const toolSelect = context.elements.inspectorContent.querySelector('[data-field="tool"]');
    toolSelect.addEventListener('change', () => {
      const tool = remoteToolReferences.find((reference) => reference.name === toolSelect.value);
      node.tool = tool?.name || '';
      node.parameters = structuredClone(tool?.input_ports || []);
      if (node.type === 'remote_sync_tool') node.outputs = structuredClone(tool?.output_ports || []);
      reconcileConnections(state);
      context.markChanged();
      context.editor.renderNodes();
      context.renderInspector();
    });
    const timeoutInput = context.elements.inspectorContent.querySelector('[data-field="timeout_ms"]');
    timeoutInput.addEventListener('input', () => {
      node.timeout_ms = Number(timeoutInput.value);
    });
    if (node.type === 'remote_async_tool') bindCallback(node);
  }

  function bindCallback(node) {
    const enabled = context.elements.inspectorContent.querySelector('[data-callback-enabled]');
    const options = context.elements.inspectorContent.querySelector('[data-callback-options]');
    const queue = options.querySelector('[data-callback-queue]');
    const eventType = options.querySelector('[data-callback-event-type]');
    const statuses = [...options.querySelectorAll('[data-callback-status]')];
    const syncCallback = () => {
      node.callback = enabled.checked ? {
        type: 'redis',
        queue: queue.value.trim(),
        event_type: eventType.value.trim(),
        on: statuses.filter((input) => input.checked).map((input) => input.value),
      } : null;
      options.hidden = !enabled.checked;
      context.markChanged();
    };
    enabled.addEventListener('change', syncCallback);
    queue.addEventListener('input', syncCallback);
    eventType.addEventListener('input', syncCallback);
    for (const input of statuses) input.addEventListener('change', syncCallback);
  }

  function bindTools(node) {
    const count = context.elements.inspectorContent.querySelector('[data-tool-count]');
    const container = context.elements.inspectorContent.querySelector('.tool-options');
    const availableNames = new Set(localToolSchemas.map((tool) => tool.name));
    const availableTools = node.tools.filter((toolName) => availableNames.has(toolName));
    if (availableTools.length !== node.tools.length) {
      node.tools = availableTools;
      context.markChanged();
    }
    const options = localToolSchemas.map((tool) => {
      const label = document.createElement('label');
      label.innerHTML = '<input type="checkbox" data-tool><span><strong></strong><small></small></span>';
      label.querySelector('input').value = tool.name;
      label.querySelector('strong').textContent = tool.name;
      label.querySelector('small').textContent = tool.description || '无描述';
      return label;
    });
    if (!options.length) options.push(Object.assign(document.createElement('div'), { className: 'empty-options', textContent: '没有已注册的 Tool' }));
    container.replaceChildren(...options);
    const inputs = context.elements.inspectorContent.querySelectorAll('[data-tool]');
    const syncCount = () => { count.textContent = `${node.tools.length} 个`; };
    for (const input of inputs) {
      input.checked = node.tools.includes(input.value);
      input.addEventListener('change', () => {
        node.tools = Array.from(inputs).filter((item) => item.checked).map((item) => item.value);
        syncCount();
        context.markChanged();
        context.editor.renderNodes();
      });
    }
    syncCount();
  }

  function bindLlm(node) {
    const toolsSection = context.elements.inspectorContent.querySelector('[data-llm-tools]');
    const think = context.elements.inspectorContent.querySelector('[data-think]');
    const toolCalls = context.elements.inspectorContent.querySelector('[data-tool-calls]');
    if (node.tool_calls === true) bindTools(node);
    else toolsSection.remove();
    think.checked = node.think === true;
    toolCalls.checked = node.tool_calls === true;
    think.addEventListener('change', () => {
      node.think = think.checked;
      reconcileConnections(state);
      context.markChanged();
      context.editor.renderNodes();
      context.renderInspector();
    });
    toolCalls.addEventListener('change', () => {
      node.tool_calls = toolCalls.checked;
      if (!node.tool_calls) node.tools = [];
      reconcileConnections(state);
      context.markChanged();
      context.editor.renderNodes();
      context.renderInspector();
    });
  }

  function setModels(models) {
    modelConfigs = models.filter((model) => model.enabled === true);
    if (nodeById(context.editor.editorState.selectedId)?.type === 'llm') context.renderInspector();
  }

  function setLocalTools(tools) {
    localToolSchemas = tools.filter((tool) => typeof tool.name === 'string' && tool.name);
    if (['llm', 'local_tool'].includes(nodeById(context.editor.editorState.selectedId)?.type)) context.renderInspector();
  }

  function setRemoteToolReferences(tools) {
    remoteToolReferences = tools.filter((tool) => typeof tool.name === 'string' && tool.name);
    if (['remote_sync_tool', 'remote_async_tool'].includes(nodeById(context.editor.editorState.selectedId)?.type)) context.renderInspector();
  }

  return { bind, prepare, setModels, setLocalTools, setRemoteToolReferences };
}