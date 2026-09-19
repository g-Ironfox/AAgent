import { reconcileConnections } from '../domain/connection-rules.js';
import { createWorkflowId } from '../domain/node-contract.js';
import { state } from '../domain/serialization.js';

export function bindStructureInspector(node, context) {
  if (node.type === 'router') bindBranches(node, context);
  if (node.type === 'construct_content') bindConstructContent(node, context);
  if (node.type === 'content_map') bindContentMap(node, context);
  if (node.type === 'deserialize_json') bindDeserializeJson(node, context);
  if (node.type === 'construct_list') bindConstructList(node, context);
  if (node.type === 'list_append') bindListAppend(node, context);
  if (node.type === 'foreach') bindForeach(node, context);
  if (node.type === 'history') bindHistory(node, context);
  if (['context_create', 'context_read', 'context_write'].includes(node.type)) bindContext(node, context);
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
      branch.name = input.value || `分支 ${index + 1}`;
      context.renderInterfaceContract(node);
      context.markChanged();
      context.editor.renderNodes();
    });
    option.querySelector('[data-delete-branch]').addEventListener('click', () => {
      if (node.branches.length <= 1) return;
      node.branches.splice(index, 1);
      commitStructureChange(node, context);
    });
    container.append(option);
  });
  context.elements.inspectorContent.querySelector('[data-add-branch]').addEventListener('click', () => {
    node.branches.push({ id: createWorkflowId('branch'), name: `分支 ${node.branches.length + 1}` });
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
  typeField.value = node.item_type;
  typeField.addEventListener('change', () => {
    node.item_type = typeField.value;
    commitStructureChange(node, context);
  });
}

function bindContext(node, context) {
  const typeField = context.elements.inspectorContent.querySelector('[data-field="value_type"]');
  typeField.value = node.value_type;
  typeField.addEventListener('change', () => {
    node.value_type = typeField.value;
    commitStructureChange(node, context);
  });
}

function bindDeserializeJson(node, context) {
  const container = context.elements.inspectorContent.querySelector('[data-json-outputs]');
  node.outputs.forEach((output, index) => {
    const row = document.createElement('div');
    row.className = 'json-output-row';
    row.innerHTML = '<span class="route-index"></span><input data-output-key maxlength="80" aria-label="JSON 键"><select data-output-type aria-label="输出类型"><option value="content">content</option><option value="message">message</option><option value="event">event</option><option value="list-content">list-content</option><option value="list-message">list-message</option><option value="event-list">event-list</option></select><button type="button" class="branch-delete" title="删除输出">×</button>';
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
  node.mappings.forEach((item, index) => {
    const row = document.createElement('div');
    row.className = 'json-output-row';
    row.innerHTML = '<span class="route-index"></span><input data-map-key maxlength="1000" aria-label="映射键" placeholder="输入"><input data-map-value maxlength="100000" aria-label="映射值" placeholder="输出"><button type="button" class="branch-delete" title="删除映射">×</button>';
    row.querySelector('.route-index').textContent = String(index + 1).padStart(2, '0');
    const keyField = row.querySelector('[data-map-key]');
    const valueField = row.querySelector('[data-map-value]');
    keyField.value = item.key;
    valueField.value = item.value;
    keyField.addEventListener('change', () => {
      const key = keyField.value;
      if (!key || node.mappings.some((mapping, mappingIndex) => mappingIndex !== index && mapping.key === key)) {
        keyField.value = item.key;
        return;
      }
      item.key = key;
      context.markChanged();
    });
    valueField.addEventListener('input', () => {
      item.value = valueField.value;
      context.markChanged();
    });
    row.querySelector('button').addEventListener('click', () => {
      if (node.mappings.length <= 1) return;
      node.mappings.splice(index, 1);
      commitStructureChange(node, context);
    });
    container.append(row);
  });
  context.elements.inspectorContent.querySelector('[data-add-content-mapping]').addEventListener('click', () => {
    let suffix = node.mappings.length + 1;
    while (node.mappings.some((item) => item.key === `key${suffix}`)) suffix += 1;
    node.mappings.push({ key: `key${suffix}`, value: '' });
    commitStructureChange(node, context);
  });
}