import { fetchEventCatalog } from './api.js';

const scopeLabels = {
  main_queue: '主队列协议',
  callback_queue: 'Tool 回调',
  display_only: '仅 WebUI 展示',
};

const state = { items: [], selected: null, view: 'tree' };
const elements = {
  catalogState: document.querySelector('#catalogState'),
  eventSearch: document.querySelector('#eventSearch'),
  eventList: document.querySelector('#eventList'),
  eventScope: document.querySelector('#eventScope'),
  eventTitle: document.querySelector('#eventTitle'),
  schemaActions: document.querySelector('#schemaActions'),
  schemaEmpty: document.querySelector('#schemaEmpty'),
  schemaContent: document.querySelector('#schemaContent'),
  eventDescription: document.querySelector('#eventDescription'),
  eventProducer: document.querySelector('#eventProducer'),
  eventConsumer: document.querySelector('#eventConsumer'),
  schemaTree: document.querySelector('#schemaTree'),
  schemaJson: document.querySelector('#schemaJson'),
  copySchema: document.querySelector('#copySchema'),
};

function describeSchema(schema) {
  if (Object.hasOwn(schema, 'const')) return `固定值 ${JSON.stringify(schema.const)}`;
  if (schema.enum) return schema.enum.map((value) => JSON.stringify(value)).join(' | ');
  if (Array.isArray(schema.type)) return schema.type.join(' | ');
  if (schema.type) return schema.type;
  return 'any';
}

function constraintText(schema) {
  const constraints = [];
  if (schema.format) constraints.push(schema.format);
  if (schema.minLength !== undefined) constraints.push(`最少 ${schema.minLength} 字符`);
  if (schema.maxLength !== undefined) constraints.push(`最多 ${schema.maxLength} 字符`);
  if (schema.maxItems !== undefined) constraints.push(`最多 ${schema.maxItems} 项`);
  if (schema.additionalProperties === false) constraints.push('不允许额外字段');
  return constraints.join(' · ');
}

function createField(name, schema, required, depth = 0) {
  const wrapper = document.createElement('div');
  wrapper.className = 'schema-field-wrap';
  const row = document.createElement('div');
  row.className = 'schema-field';
  row.style.setProperty('--depth', depth);

  const hasChildren = schema.properties && Object.keys(schema.properties).length > 0;
  const toggle = document.createElement('button');
  toggle.type = 'button';
  toggle.className = 'field-toggle';
  toggle.disabled = !hasChildren;
  toggle.setAttribute('aria-label', hasChildren ? `折叠 ${name}` : `${name} 没有子字段`);
  toggle.setAttribute('aria-expanded', 'true');
  toggle.textContent = hasChildren ? '−' : '·';

  const identity = document.createElement('div');
  identity.className = 'field-identity';
  const fieldName = document.createElement('code');
  fieldName.textContent = name;
  identity.append(fieldName);
  if (required) {
    const marker = document.createElement('span');
    marker.className = 'required-marker';
    marker.textContent = '必填';
    identity.append(marker);
  }

  const type = document.createElement('span');
  type.className = 'field-type';
  type.textContent = describeSchema(schema);
  const constraint = document.createElement('span');
  constraint.className = 'field-constraint';
  constraint.textContent = constraintText(schema);
  row.append(toggle, identity, type, constraint);
  wrapper.append(row);

  if (hasChildren) {
    const children = document.createElement('div');
    children.className = 'schema-children';
    const requiredFields = new Set(schema.required || []);
    Object.entries(schema.properties).forEach(([childName, childSchema]) => {
      children.append(createField(childName, childSchema, requiredFields.has(childName), depth + 1));
    });
    toggle.addEventListener('click', () => {
      const expanded = toggle.getAttribute('aria-expanded') === 'true';
      toggle.setAttribute('aria-expanded', String(!expanded));
      toggle.textContent = expanded ? '+' : '−';
      children.hidden = expanded;
    });
    wrapper.append(children);
  }
  return wrapper;
}

function renderSchema(item) {
  state.selected = item;
  elements.eventScope.textContent = scopeLabels[item.scope].toUpperCase();
  elements.eventTitle.textContent = item.event_type;
  elements.eventDescription.textContent = item.description;
  elements.eventProducer.textContent = item.producer;
  elements.eventConsumer.textContent = item.consumer;
  elements.schemaTree.replaceChildren(createField('event', item.schema, true));
  elements.schemaJson.querySelector('code').textContent = JSON.stringify(item.schema, null, 2);
  elements.schemaEmpty.hidden = true;
  elements.schemaContent.hidden = false;
  elements.schemaActions.hidden = false;
  renderList();
}

function renderList() {
  const query = elements.eventSearch.value.trim().toLowerCase();
  const visible = state.items.filter((item) =>
    [item.event_type, item.title, item.description, scopeLabels[item.scope]].join(' ').toLowerCase().includes(query)
  );
  elements.eventList.replaceChildren();
  Object.keys(scopeLabels).forEach((scope) => {
    const scopedItems = visible.filter((item) => item.scope === scope);
    if (!scopedItems.length) return;
    const group = document.createElement('section');
    group.className = 'event-group';
    const heading = document.createElement('h3');
    heading.textContent = scopeLabels[scope];
    group.append(heading);
    scopedItems.forEach((item) => {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'event-item';
      if (state.selected?.event_type === item.event_type) button.classList.add('active');
      const name = document.createElement('code');
      name.textContent = item.event_type;
      const title = document.createElement('span');
      title.textContent = item.title;
      button.append(name, title);
      button.addEventListener('click', () => renderSchema(item));
      group.append(button);
    });
    elements.eventList.append(group);
  });
  if (!visible.length) {
    const empty = document.createElement('p');
    empty.className = 'event-list-empty';
    empty.textContent = '没有匹配的事件类型';
    elements.eventList.append(empty);
  }
}

function setView(view) {
  state.view = view;
  elements.schemaTree.hidden = view !== 'tree';
  elements.schemaJson.hidden = view !== 'json';
  document.querySelectorAll('[data-view]').forEach((button) => {
    const active = button.dataset.view === view;
    button.classList.toggle('active', active);
    button.setAttribute('aria-pressed', String(active));
  });
}

elements.eventSearch.addEventListener('input', renderList);
document.querySelectorAll('[data-view]').forEach((button) => {
  button.addEventListener('click', () => setView(button.dataset.view));
});
elements.copySchema.addEventListener('click', async () => {
  if (!state.selected) return;
  await navigator.clipboard.writeText(JSON.stringify(state.selected.schema, null, 2));
  elements.copySchema.classList.add('copied');
  window.setTimeout(() => elements.copySchema.classList.remove('copied'), 900);
});

try {
  const catalog = await fetchEventCatalog();
  state.items = catalog.items;
  elements.catalogState.textContent = String(catalog.count);
  renderList();
  if (state.items.length) renderSchema(state.items[0]);
} catch (error) {
  elements.catalogState.textContent = '读取失败';
  elements.catalogState.classList.add('error');
  elements.schemaEmpty.innerHTML = '';
  const message = document.createElement('strong');
  message.textContent = error.message;
  elements.schemaEmpty.append(message);
}