import { reconcileConnections } from '../domain/connection-rules.js';
import { createWorkflowId } from '../domain/node-contract.js';
import { state } from '../domain/serialization.js';

export function bindStructureInspector(node, context) {
  if (node.type === 'router') bindBranches(node, context);
  if (['construct_struct', 'struct_get', 'struct_update', 'struct_to_json', 'json_to_struct'].includes(node.type)) bindStructNodes(node, context);
  if (node.type === 'construct_content') bindConstructContent(node, context);
  if (node.type === 'construct_map_content') bindContentMap(node, context);
  if (node.type === 'deserialize_json') bindDeserializeJson(node, context);
  if (node.type === 'construct_list') bindConstructList(node, context);
  if (node.type === 'list_append') bindListAppend(node, context);
  if (node.type === 'foreach') bindForeach(node, context);
  if (node.type === 'history') bindHistory(node, context);
  if (['context_create', 'context_read', 'context_write', 'session_create', 'session_read', 'session_write'].includes(node.type)) bindContext(node, context);
}


function localStructs() { return state.metadata?.structs || []; }

function addTypeOptions(select, { includeBuiltin = false, includeStructLists = false } = {}) {
  const existing = new Set([...select.options].map((option) => option.value));
  if (includeBuiltin) {
    for (const type of ['content', 'message', 'event', 'map-content', 'list-content', 'list-message', 'list-event']) {
      if (!existing.has(type)) select.add(new Option(type, type));
    }
  }
  for (const definition of localStructs()) {
    const type = `struct:${definition.id}`;
    if (!existing.has(type)) select.add(new Option(definition.name, type));
    if (includeStructLists) {
      const listType = `list-struct:${definition.id}`;
      if (!existing.has(listType)) select.add(new Option(`List<${definition.name}>`, listType));
    }
  }
}

function commitStructMutation(node, context, previous, connections) {
  reconcileConnections(state);
  const removed = state.connections.length < connections.length;
  if (removed && !window.confirm('此更改会移除不再匹配的连线，继续吗？')) {
    for (const key of Object.keys(node)) delete node[key];
    Object.assign(node, previous);
    state.connections = connections;
    context.editor.renderNodes();
    context.renderInspector();
    return false;
  }
  context.markChanged();
  context.editor.renderNodes();
  context.renderInspector();
  return true;
}

function bindStructNodes(node, context) {
  const definitions = localStructs();
  const byId = new Map(definitions.map((definition) => [definition.id, definition]));
  const structSelect = context.elements.inspectorContent.querySelector('[data-struct-id]');
  if (structSelect) {
    structSelect.add(new Option(definitions.length ? '选择 Struct 类型' : '尚无 Struct 声明', ''));
    for (const definition of definitions) structSelect.add(new Option(definition.name, definition.id));
    structSelect.value = node.struct_id || '';
    structSelect.addEventListener('change', () => {
      const previous = structuredClone(node); const connections = structuredClone(state.connections);
      const definition = byId.get(structSelect.value);
      if (!definition) {
        node.struct_id = '';
        if (node.type === 'construct_struct') node.dataInputPorts = [];
        if (node.type === 'struct_get') Object.assign(node, { field: '', missing: 'error', has_fallback: false, dataInputPorts: [] });
        if (node.type === 'struct_update') Object.assign(node, { updates: [], remove_fields: [], dataInputPorts: [] });
        commitStructMutation(node, context, previous, connections);
        return;
      }
      node.struct_id = definition.id;
      if (node.type === 'construct_struct') node.dataInputPorts = definition.fields.map((field) => field.name);
      if (node.type === 'struct_get') { node.field = definition.fields[0]?.name || ''; node.missing = 'error'; node.has_fallback = false; node.dataInputPorts = ['struct-in']; }
      if (node.type === 'struct_update') { node.updates = []; node.remove_fields = []; node.dataInputPorts = ['struct-in']; }
      commitStructMutation(node, context, previous, connections);
    });
  }
  if (node.type === 'construct_struct') {
    const mount = context.elements.inspectorContent.querySelector('[data-struct-fields]');
    const definition = byId.get(node.struct_id);
    if (mount && !definition) {
      const help = document.createElement('p'); help.className = 'empty-options'; help.textContent = '先在 Inspector 中选择 Struct 类型'; mount.replaceChildren(help);
    } else if (mount && definition) {
      mount.innerHTML = '<div class="section-label"><strong>字段输入</strong></div>';
      for (const field of definition.fields) {
        const row = document.createElement('div'); row.className = 'parameter-row';
        const text = document.createElement('span'); text.textContent = field.name;
        const type = document.createElement('small'); type.textContent = field.type + (field.required ? ' · 必需' : ' · 可选');
        row.append(text, type); mount.append(row);
      }
    }
  }
  if (node.type === 'struct_get') {
    const definition = byId.get(node.struct_id);
    const fieldSelect = context.elements.inspectorContent.querySelector('[data-struct-field]');
    const missingSelect = context.elements.inspectorContent.querySelector('[data-struct-missing]');
    if (fieldSelect && !definition) {
      fieldSelect.add(new Option('先选择 Struct 类型', ''));
      fieldSelect.disabled = true;
      missingSelect.disabled = true;
    }
    if (definition && fieldSelect && missingSelect) {
      if (!definition.fields.length) fieldSelect.add(new Option('Struct 尚无字段', ''));
      for (const field of definition.fields) fieldSelect.add(new Option(`${field.name}: ${field.type}`, field.name));
      fieldSelect.value = node.field; missingSelect.value = node.missing || 'error';
      const apply = () => {
        const field = definition.fields.find((item) => item.name === fieldSelect.value);
        const previous = structuredClone(node); const connections = structuredClone(state.connections);
        node.field = fieldSelect.value;
        if (!field || field.required) { node.missing = 'error'; missingSelect.value = 'error'; } else node.missing = missingSelect.value;
        node.has_fallback = node.missing === 'fallback';
        node.dataInputPorts = node.has_fallback ? ['struct-in', 'fallback-in'] : ['struct-in'];
        commitStructMutation(node, context, previous, connections);
      };
      fieldSelect.addEventListener('change', apply); missingSelect.addEventListener('change', apply);
      const selected = definition.fields.find((field) => field.name === node.field);
      if (selected?.required) missingSelect.options[1].disabled = true;
    }
  }
  if (node.type === 'struct_update') {
    const definition = byId.get(node.struct_id); const mount = context.elements.inspectorContent.querySelector('[data-struct-update-fields]');
    if (mount && !definition) {
      const help = document.createElement('p'); help.className = 'empty-options'; help.textContent = '先在 Inspector 中选择 Struct 类型'; mount.replaceChildren(help);
    } else if (definition && mount) {
      mount.replaceChildren();
      for (const field of definition.fields) {
        const label = document.createElement('label'); label.className = 'struct-update-row';
        const name = document.createElement('span'); name.textContent = field.name;
        const operation = document.createElement('select'); operation.setAttribute('aria-label', field.name + ' 操作');
        for (const [value, text] of [['keep','保留'],['update','替换'],['remove','移除']]) operation.add(new Option(text, value));
        operation.value = node.updates.includes(field.name) ? 'update' : node.remove_fields.includes(field.name) ? 'remove' : 'keep';
        if (field.required) operation.options[2].disabled = true;
        operation.addEventListener('change', () => {
          const previous = structuredClone(node); const connections = structuredClone(state.connections);
          node.updates = node.updates.filter((item) => item !== field.name); node.remove_fields = node.remove_fields.filter((item) => item !== field.name);
          if (operation.value === 'update') node.updates.push(field.name);
          if (operation.value === 'remove') node.remove_fields.push(field.name);
          node.dataInputPorts = ['struct-in', ...node.updates];
          commitStructMutation(node, context, previous, connections);
        });
        label.append(name, operation); mount.append(label);
      }
    }
  }
  const valueType = context.elements.inspectorContent.querySelector('[data-struct-value-type]');
  if (valueType) {
    valueType.add(new Option(definitions.length ? '选择 Struct 类型' : '尚无 Struct 声明', ''));
    addTypeOptions(valueType, { includeStructLists: true }); valueType.value = node.value_type || '';
    valueType.addEventListener('change', () => {
      const previous = structuredClone(node); const connections = structuredClone(state.connections);
      node.value_type = valueType.value; commitStructMutation(node, context, previous, connections);
    });
  }
}

function commitStructureChange(node, context, renderInspector = true) {
  reconcileConnections(state);
  context.markChanged();
  context.editor.renderNodes();
  if (renderInspector) context.renderInspector();
}

function bindBranches(node, context) {
  const container = context.elements.inspectorContent.querySelector('[data-route-options]');
  node.branches.forEach((branch, index) => {
    const option = document.createElement('div');
    option.className = 'route-option';
    option.innerHTML = '<span class="route-index"></span><label><input data-branch-name maxlength="30"><small>控制流输出分支</small></label><button type="button" class="branch-delete" data-delete-branch title="删除分支">×</button>';
    option.querySelector('.route-index').textContent = String(index + 1).padStart(2, '0');
    const input = option.querySelector('[data-branch-name]');
    input.value = branch.name;
    input.addEventListener('input', () => {
      const name = input.value || `分支 ${index + 1}`;
      if (node.branches.some((candidate) => candidate !== branch && candidate.name === name)) {
        input.value = branch.name;
        return;
      }
      branch.name = name;
      input.value = branch.name;
      context.renderInterfaceContract(node);
      context.markChanged();
      context.editor.renderNodes();
    });
    option.querySelector('[data-delete-branch]').addEventListener('click', () => {
      node.branches.splice(node.branches.indexOf(branch), 1);
      commitStructureChange(node, context);
    });
    container.append(option);
  });
  context.elements.inspectorContent.querySelector('[data-add-branch]').addEventListener('click', () => {
    let suffix = node.branches.length + 1;
    while (node.branches.some((branch) => branch.name === `分支 ${suffix}`)) suffix += 1;
    node.branches.push({ id: createWorkflowId('branch'), name: `分支 ${suffix}` });
    commitStructureChange(node, context);
  });
}

function bindConstructContent(node, context) {
  const container = context.elements.inspectorContent.querySelector('[data-append-items]');
  const syncPorts = () => {
    const usedPorts = new Set();
    let portIndex = 0;
    node.append_items.forEach((item) => {
      if (item.type !== 'port') return;
      while (usedPorts.has(item.port_id) || !item.port_id) item.port_id = `append-in-${portIndex++}`;
      usedPorts.add(item.port_id);
    });
    node.dataInputPorts = node.append_items.filter((item) => item.type === 'port').map((item) => item.port_id);
  };
  const render = () => {
    syncPorts();
    context.renderInterfaceContract(node);
    container.replaceChildren(...node.append_items.map((item, index) => {
      const row = document.createElement('div');
      row.className = 'append-item';
      row.innerHTML = '<div class="append-item-head"><span class="route-index"></span><select aria-label="内容项来源"><option value="port">Port 输入</option><option value="fixed">固定内容</option></select><button type="button" class="branch-delete" title="删除内容项">×</button></div><div class="append-item-body"><code data-append-port></code><textarea rows="3" maxlength="100000" aria-label="固定内容"></textarea><small></small></div>';
      row.querySelector('.route-index').textContent = String(index + 1).padStart(2, '0');
      const select = row.querySelector('select');
      const portName = row.querySelector('[data-append-port]');
      const input = row.querySelector('textarea');
      select.value = item.type;
      portName.textContent = item.type === 'port' ? item.port_id : '';
      portName.hidden = item.type !== 'port';
      input.value = item.type === 'fixed' ? item.value : '';
      input.hidden = item.type !== 'fixed';
      input.placeholder = '输入固定内容';
      input.addEventListener('input', () => {
        if (item.type === 'fixed') item.value = input.value;
        context.markChanged();
        context.editor.renderNodes();
      });
      select.addEventListener('change', () => {
        item.type = select.value;
        if (item.type === 'port') item.port_id = '';
        else item.value = '';
        syncPorts();
        reconcileConnections(state);
        context.markChanged();
        context.editor.renderNodes();
        render();
      });
      row.querySelector('small').textContent = item.type === 'port' ? '连接 content 到此输入端口' : '内容会在此顺序位置拼接';
      row.querySelector('button').addEventListener('click', () => {
        if (node.append_items.length <= 1) return;
        node.append_items.splice(index, 1);
        syncPorts();
        reconcileConnections(state);
        context.markChanged();
        context.editor.renderNodes();
        render();
      });
      return row;
    }));
  };
  render();
  context.elements.inspectorContent.querySelector('[data-add-append]').addEventListener('click', () => {
    node.append_items.push({ type: 'fixed', value: '' });
    context.markChanged();
    render();
    context.editor.renderNodes();
  });
}

function bindConstructList(node, context) {
  const typeField = context.elements.inspectorContent.querySelector('[data-field="item_type"]');
  addTypeOptions(typeField);
  const countField = context.elements.inspectorContent.querySelector('[data-field="initial_value_count"]');
  typeField.value = node.item_type;
  countField.value = node.initial_value_count;
  typeField.addEventListener('change', () => {
    node.item_type = typeField.value;
    node.dataInputPorts = node.dataInputPorts.map((_, index) => `${node.item_type}-in-${index}`);
    commitStructureChange(node, context);
  });
  countField.addEventListener('change', () => {
    node.initial_value_count = Math.min(20, Math.max(0, Number.parseInt(countField.value, 10) || 0));
    node.dataInputPorts = Array.from({ length: node.initial_value_count }, (_, index) => `${node.item_type}-in-${index}`);
    commitStructureChange(node, context);
  });
}

function bindForeach(node, context) {
  const typeField = context.elements.inspectorContent.querySelector('[data-field="item_type"]');
  addTypeOptions(typeField);
  typeField.value = node.item_type;
  typeField.addEventListener('change', () => {
    node.item_type = typeField.value;
    commitStructureChange(node, context);
  });
}

function bindHistory(node, context) {
  const eventTypeFields = context.elements.inspectorContent.querySelectorAll('[data-history-event-type]');
  const limitField = context.elements.inspectorContent.querySelector('[data-field="limit"]');
  for (const field of eventTypeFields) {
    field.checked = node.event_types.includes(field.value);
    field.addEventListener('change', () => {
      const selected = [...eventTypeFields].filter((option) => option.checked).map((option) => option.value);
      if (!selected.length) {
        field.checked = true;
        return;
      }
      node.event_types = selected;
      context.markChanged();
    });
  }
  limitField.value = node.limit;
  limitField.addEventListener('change', () => {
    node.limit = Math.min(1000, Math.max(1, Number.parseInt(limitField.value, 10) || 1));
    limitField.value = node.limit;
    context.markChanged();
  });
}

function bindListAppend(node, context) {
  const typeField = context.elements.inspectorContent.querySelector('[data-field="item_type"]');
  addTypeOptions(typeField);
  typeField.value = node.item_type;
  typeField.addEventListener('change', () => {
    node.item_type = typeField.value;
    commitStructureChange(node, context);
  });
}

function bindContext(node, context) {
  const typeField = context.elements.inspectorContent.querySelector('[data-field="value_type"]');
  if (node.type.startsWith('context_')) addTypeOptions(typeField, { includeStructLists: true });
  typeField.value = node.value_type;
  typeField.addEventListener('change', () => {
    node.value_type = typeField.value;
    commitStructureChange(node, context);
  });
  if (node.type === 'context_create') {
    const idField = context.elements.inspectorContent.querySelector('[data-field="context_id"]');
    idField.value = node.context_id || '';
    idField.addEventListener('change', () => {
      node.context_id = idField.value;
      commitStructureChange(node, context, false);
    });
  }
  if (node.type === 'context_read' || node.type === 'context_write') {
    const sourceField = context.elements.inspectorContent.querySelector('[data-field="context_id_source"]');
    const idField = context.elements.inspectorContent.querySelector('[data-field="context_id"]');
    const idContainer = context.elements.inspectorContent.querySelector('[data-context-id-field]');
    sourceField.value = node.context_id_source === 'fixed' ? 'fixed' : 'port';
    idField.value = node.context_id || '';
    idContainer.hidden = sourceField.value !== 'fixed';
    sourceField.addEventListener('change', () => {
      node.context_id_source = sourceField.value;
      idContainer.hidden = sourceField.value !== 'fixed';
      commitStructureChange(node, context);
    });
    idField.addEventListener('change', () => {
      node.context_id = idField.value;
      commitStructureChange(node, context, false);
    });
  }
}

function bindDeserializeJson(node, context) {
  const container = context.elements.inspectorContent.querySelector('[data-json-outputs]');
  node.outputs.forEach((output, index) => {
    const row = document.createElement('div');
    row.className = 'json-output-row';
    row.innerHTML = '<span class="route-index"></span><input data-output-key maxlength="80" aria-label="JSON 键"><select data-output-type aria-label="输出类型"><option value="content">content</option><option value="message">message</option><option value="event">event</option><option value="list-content">list-content</option><option value="list-message">list-message</option><option value="list-event">list-event</option></select><button type="button" class="branch-delete" title="删除输出">×</button>';
    row.querySelector('.route-index').textContent = String(index + 1).padStart(2, '0');
    const keyField = row.querySelector('[data-output-key]');
    const typeField = row.querySelector('[data-output-type]');
    keyField.value = output.key;
    typeField.value = output.type;
    keyField.addEventListener('change', () => {
      const key = keyField.value.trim();
      if (!key || key === 'control-out' || node.outputs.some((item, itemIndex) => itemIndex !== index && item.key === key)) {
        keyField.value = output.key;
        return;
      }
      output.key = key;
      commitStructureChange(node, context);
    });
    typeField.addEventListener('change', () => {
      output.type = typeField.value;
      commitStructureChange(node, context);
    });
    row.querySelector('button').addEventListener('click', () => {
      if (node.outputs.length <= 1) return;
      node.outputs.splice(index, 1);
      commitStructureChange(node, context);
    });
    container.append(row);
  });
  context.elements.inspectorContent.querySelector('[data-add-json-output]').addEventListener('click', () => {
    let suffix = node.outputs.length + 1;
    while (node.outputs.some((output) => output.key === `value${suffix}`)) suffix += 1;
    node.outputs.push({ key: `value${suffix}`, type: 'content' });
    commitStructureChange(node, context);
  });
}

function bindContentMap(node, context) {
  const container = context.elements.inspectorContent.querySelector('[data-content-mappings]');
  const syncPorts = () => {
    const usedPorts = new Set();
    node.mappings.forEach((item, index) => {
      if (item.value_source !== 'port') return;
      if (!item.port_id || usedPorts.has(item.port_id)) item.port_id = `map-value-in-${index}`;
      usedPorts.add(item.port_id);
    });
    node.dataInputPorts = node.mappings
      .filter((item) => item.value_source === 'port')
      .map((item) => item.port_id);
  };
  node.mappings.forEach((item, index) => {
    const row = document.createElement('div');
    row.className = 'append-item';
    row.innerHTML = '<div class="append-item-head"><span class="route-index"></span><input data-map-key maxlength="1000" aria-label="映射键" placeholder="键"><button type="button" class="branch-delete" title="删除映射">×</button></div><div class="append-item-body"><select aria-label="映射值来源"><option value="fixed">固定值</option><option value="port">端口输入</option></select><textarea data-map-value rows="3" maxlength="100000" aria-label="映射值"></textarea><code data-map-port></code></div>';
    row.querySelector('.route-index').textContent = String(index + 1).padStart(2, '0');
    const keyField = row.querySelector('[data-map-key]');
    const sourceField = row.querySelector('select');
    const valueField = row.querySelector('[data-map-value]');
    const portName = row.querySelector('[data-map-port]');
    sourceField.value = item.value_source === 'port' ? 'port' : 'fixed';
    keyField.value = item.key;
    valueField.value = sourceField.value === 'fixed' ? item.value : '';
    portName.textContent = sourceField.value === 'port' ? item.port_id : '';
    valueField.hidden = sourceField.value !== 'fixed';
    portName.hidden = sourceField.value !== 'port';
    sourceField.addEventListener('change', () => {
      if (sourceField.value === 'port') {
        const usedPorts = new Set(node.dataInputPorts || []);
        let suffix = 0;
        while (usedPorts.has(`map-value-in-${suffix}`)) suffix += 1;
        item.value_source = 'port';
        item.port_id = `map-value-in-${suffix}`;
        delete item.value;
      } else {
        item.value = '';
        delete item.value_source;
        delete item.port_id;
      }
      syncPorts();
      commitStructureChange(node, context);
    });
    keyField.addEventListener('change', () => {
      const key = keyField.value;
      if (!key || node.mappings.some((mapping, mappingIndex) => mappingIndex !== index && mapping.key === key)) {
        keyField.value = item.key;
        return;
      }
      item.key = key;
      context.markChanged();
      context.renderInterfaceContract(node);
      context.editor.renderNodes();
    });
    valueField.addEventListener('input', () => {
      item.value = valueField.value;
      context.markChanged();
    });
    row.querySelector('button').addEventListener('click', () => {
      if (node.mappings.length <= 1) return;
      node.mappings.splice(index, 1);
      syncPorts();
      commitStructureChange(node, context);
    });
    container.append(row);
  });
  context.elements.inspectorContent.querySelector('[data-add-content-mapping]').addEventListener('click', () => {
    let suffix = node.mappings.length + 1;
    while (node.mappings.some((item) => item.key === `key${suffix}`)) suffix += 1;
    node.mappings.push({ key: `key${suffix}`, value: '' });
    syncPorts();
    commitStructureChange(node, context);
  });
}
