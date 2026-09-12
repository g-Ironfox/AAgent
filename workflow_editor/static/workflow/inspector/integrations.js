import { reconcileConnections } from '../domain/connection-rules.js';
import { nodeById, state } from '../domain/serialization.js';

export function createIntegrationInspector(context) {
  let modelConfigs = [];
  let toolSchemas = [];

  function prepare(node) {
    if (node.type === 'llm') renderModelOptions(node);
    if (node.type === 'tool') renderToolSelect(node);
    if (node.type === 'workflow') context.elements.inspectorContent.querySelector('[data-workflow-name]').value = node.workflow_name;
  }

  function bind(node) {
    if (node.type === 'llm') bindLlm(node);
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

  function renderToolSelect(node) {
    const select = context.elements.inspectorContent.querySelector('[data-field="tool"]');
    const selectedSchema = toolSchemas.find((tool) => tool.name === node.tool);
    if (selectedSchema) node.parameters = Object.keys(selectedSchema.parameters?.properties || {});
    if (!node.tool && toolSchemas.length) {
      node.tool = toolSchemas[0].name;
      node.parameters = Object.keys(toolSchemas[0].parameters?.properties || {});
      context.markChanged();
    }
    const options = toolSchemas.map((tool) => {
      const option = Object.assign(document.createElement('option'), { value: tool.name, textContent: tool.name });
      option.title = tool.description || '';
      return option;
    });
    if (!toolSchemas.some((tool) => tool.name === node.tool)) {
      options.unshift(Object.assign(document.createElement('option'), {
        value: node.tool || '',
        textContent: node.tool ? `当前未注册 (${node.tool})` : '没有已注册的 Tool',
      }));
    }
    select.replaceChildren(...options);
    select.disabled = toolSchemas.length === 0;
    select.addEventListener('change', () => {
      const schema = toolSchemas.find((tool) => tool.name === select.value);
      node.tool = select.value;
      node.parameters = Object.keys(schema?.parameters?.properties || {});
      reconcileConnections(state);
      context.markChanged();
      context.editor.renderNodes();
      context.renderInspector();
    });
  }

  function bindTools(node) {
    const count = context.elements.inspectorContent.querySelector('[data-tool-count]');
    const container = context.elements.inspectorContent.querySelector('.tool-options');
    const availableNames = new Set(toolSchemas.map((tool) => tool.name));
    const unavailableTools = node.tools.filter((toolName) => !availableNames.has(toolName));
    const options = toolSchemas.map((tool) => {
      const label = document.createElement('label');
      label.innerHTML = '<input type="checkbox" data-tool><span><strong></strong><small></small></span>';
      label.querySelector('input').value = tool.name;
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
    if (!options.length) options.push(Object.assign(document.createElement('div'), { className: 'empty-options', textContent: '没有已注册的 Tool' }));
    container.replaceChildren(...options);
    const inputs = context.elements.inspectorContent.querySelectorAll('[data-tool]');
    const syncCount = () => { count.textContent = `${node.tools.length} 个`; };
    for (const input of inputs) {
      input.checked = node.tools.includes(input.value);
      input.addEventListener('change', () => {
        node.tools = [...unavailableTools, ...Array.from(inputs).filter((item) => item.checked && !item.disabled).map((item) => item.value)];
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

  function setTools(tools) {
    toolSchemas = tools.filter((tool) => typeof tool.name === 'string' && tool.name);
    if (['llm', 'tool'].includes(nodeById(context.editor.editorState.selectedId)?.type)) context.renderInspector();
  }

  return { bind, prepare, setModels, setTools };
}