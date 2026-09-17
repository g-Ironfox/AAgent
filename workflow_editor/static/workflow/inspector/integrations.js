import { reconcileConnections } from '../domain/connection-rules.js';
import { nodeById, state } from '../domain/serialization.js';

export function createIntegrationInspector(context) {
  let modelConfigs = [];
  let localToolSchemas = [];
  let remoteToolSchemas = [];

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

  function workflowType(schema) {
    const declared = schema?.['x-workflow-port-type'];
    if (['content', 'message', 'list-content', 'list-message'].includes(declared)) return declared;
    return schema?.type === 'array' ? 'list-content' : 'content';
  }

  function schemaPorts(schema, defaultName = null) {
    if (!schema || typeof schema !== 'object') return [];
    if (schema.properties && typeof schema.properties === 'object') {
      return Object.entries(schema.properties).map(([name, property]) => ({ name, type: workflowType(property) }));
    }
    return defaultName ? [{ name: defaultName, type: workflowType(schema) }] : [];
  }

  function renderPortRows(node, key, reservedName) {
    const container = context.elements.inspectorContent.querySelector(`[data-remote-${key}]`);
    if (!container) return;
    const rows = node[key].map((port) => {
      const row = document.createElement('div');
      row.className = 'parameter-row';
      row.innerHTML = '<input maxlength="80" aria-label="端口名称"><select aria-label="端口类型"><option value="content">content</option><option value="message">message</option><option value="list-content">list-content</option><option value="list-message">list-message</option></select><button type="button" title="删除端口" aria-label="删除端口">×</button>';
      const input = row.querySelector('input');
      input.value = port.name;
      input.classList.toggle('invalid', !port.name || port.name === reservedName);
      row.querySelector('select').value = port.type;
      return row;
    });
    container.replaceChildren(...rows);
    if (!rows.length) container.append(Object.assign(document.createElement('div'), { className: 'empty-options', textContent: '暂无端口' }));
  }

  function renderRemoteToolFields(node) {
    const candidates = context.elements.inspectorContent.querySelector('#remoteToolCandidates');
    candidates.replaceChildren();
    renderPortRows(node, 'parameters', 'control-in');
    if (node.type === 'remote_sync_tool') renderPortRows(node, 'outputs', 'control-out');
  }

  function bindRemoteTool(node) {
    const bindPortRows = (key, reservedName) => {
      const container = context.elements.inspectorContent.querySelector(`[data-remote-${key}]`);
      if (!container) return;
      const syncPorts = () => {
      const rows = [...container.querySelectorAll('.parameter-row')];
      const inputs = rows.map((row) => row.querySelector('input'));
      node[key] = rows.map((row) => ({
        name: row.querySelector('input').value.trim(),
        type: row.querySelector('select').value,
      }));
      for (const input of inputs) input.classList.toggle('invalid', !input.value.trim() || input.value.trim() === reservedName);
      reconcileConnections(state);
      context.markChanged();
      context.editor.renderNodes();
      context.renderInterfaceContract(node);
      };
      for (const row of container.querySelectorAll('.parameter-row')) {
        row.querySelector('input').addEventListener('input', syncPorts);
        row.querySelector('select').addEventListener('change', syncPorts);
        row.querySelector('button').addEventListener('click', () => {
          row.remove();
          syncPorts();
          context.renderInspector();
        });
      }
      context.elements.inspectorContent.querySelector(`[data-add-remote-${key.slice(0, -1)}]`).addEventListener('click', () => {
        const prefix = key === 'parameters' ? 'parameter' : 'result';
        let index = node[key].length + 1;
        while (node[key].some((port) => port.name === `${prefix}_${index}`)) index += 1;
        node[key].push({ name: `${prefix}_${index}`, type: 'content' });
        context.markChanged();
        context.renderInspector();
      });
    };
    bindPortRows('parameters', 'control-in');
    if (node.type === 'remote_sync_tool') bindPortRows('outputs', 'control-out');
    const toolInput = context.elements.inspectorContent.querySelector('[data-field="tool"]');
    const candidates = context.elements.inspectorContent.querySelector('#remoteToolCandidates');
    const selectTool = (schema) => {
      toolInput.value = schema.name;
      node.tool = schema.name;
      node.parameters = schemaPorts(schema.inputSchema);
      if (node.type === 'remote_sync_tool') node.outputs = schemaPorts(schema.outputSchema, 'result');
      reconcileConnections(state);
      context.markChanged();
      context.editor.renderNodes();
      context.renderInspector();
    };
    const renderCandidates = () => {
      const query = toolInput.value.trim().toLocaleLowerCase();
      const matches = remoteToolSchemas.filter((tool) => !query || tool.name.toLocaleLowerCase().includes(query));
      candidates.replaceChildren(...matches.map((tool) => {
        const option = document.createElement('button');
        option.type = 'button';
        option.className = 'remote-tool-candidate';
        option.setAttribute('role', 'option');
        option.innerHTML = '<strong></strong><small></small>';
        option.querySelector('strong').textContent = tool.name;
        option.querySelector('small').textContent = tool.description || '无描述';
        option.addEventListener('pointerdown', (event) => {
          event.preventDefault();
          selectTool(tool);
        });
        return option;
      }));
      candidates.hidden = matches.length === 0;
    };
    toolInput.addEventListener('focus', renderCandidates);
    toolInput.addEventListener('input', renderCandidates);
    toolInput.addEventListener('blur', () => { candidates.hidden = true; });
    const timeoutInput = context.elements.inspectorContent.querySelector('[data-field="timeout_ms"]');
    timeoutInput.addEventListener('input', () => {
      node.timeout_ms = Number(timeoutInput.value);
    });
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

  function setRemoteTools(tools) {
    remoteToolSchemas = tools.filter((tool) => typeof tool.name === 'string' && tool.name);
    if (['remote_sync_tool', 'remote_async_tool'].includes(nodeById(context.editor.editorState.selectedId)?.type)) context.renderInspector();
  }

  return { bind, prepare, setModels, setLocalTools, setRemoteTools };
}