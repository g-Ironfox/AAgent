const statusText = { running: '正在执行', pending: '等待执行', done: '执行历史' };
const sourceText = { worker: 'Worker', redis: 'Redis', mongodb: 'MongoDB' };
const emptyText = {
  done: ['MongoDB 没有历史记录', '当前筛选没有匹配的历史事件'],
  running: ['当前无执行事件', '当前执行不符合筛选条件'],
  pending: ['Redis 队列已清空', '等待队列中没有匹配事件'],
};
const sourceByStatus = { done: 'mongodb', running: 'worker', pending: 'redis' };

let deleteHandler = null;
let editHandler = null;
const expandedKeys = new Set();

export function setEventDeleteHandler(handler) {
  deleteHandler = handler;
}

export function setEventEditHandler(handler) {
  editHandler = handler;
}

function itemKey(item) {
  if (item.status === 'done') return `done:${item.doc_id}`;
  if (item.status === 'pending') return `pending:${item.fingerprint}:${item.position}`;
  return `running:${item.id}`;
}

export function remapExpandedKey(previous, next) {
  const oldKey = itemKey(previous);
  if (!expandedKeys.has(oldKey)) return;
  expandedKeys.delete(oldKey);
  expandedKeys.add(itemKey(next));
}

export function eventType(item) {
  return String(item.event?.event_type || '未分类');
}

export function eventPreview(item) {
  const render = item.event?.render;
  if (typeof render === 'string' && render.trim()) {
    return render;
  }
  const payload = item.event?.payload;
  if (item.event?.event_type === 'active') {
    return '请求 LLM 处理';
  }
  const candidates = [payload?.raw_message, payload?.content, payload?.result, payload?.message, payload?.tool, payload?.raw];
  const text = candidates.find((value) => typeof value === 'string' && value.trim());
  return text ? text.slice(0, 260) : JSON.stringify(payload ?? item.event).slice(0, 260);
}

export function eventTime(item) {
  if (item.status === 'pending') return item.position === 1 ? '下一项' : `等待 #${item.position}`;
  const value = item.started_at || item.created_at;
  const date = value ? new Date(value) : null;
  return date && !Number.isNaN(date.getTime())
    ? date.toLocaleString('zh-CN', { hour12: false })
    : '时间未知';
}

export function populateTypes(container, items, selected) {
  const types = [...new Set(items.map(eventType))].sort((left, right) => left.localeCompare(right, 'zh-CN'));
  for (const value of [...selected]) {
    if (!types.includes(value)) selected.delete(value);
  }
  const fragment = document.createDocumentFragment();
  const clear = document.createElement('button');
  clear.type = 'button';
  clear.className = 'type-filter-clear';
  clear.textContent = '全部类型';
  fragment.append(clear);
  for (const type of types) {
    const label = document.createElement('label');
    label.className = 'type-filter-option';
    const box = document.createElement('input');
    box.type = 'checkbox';
    box.value = type;
    box.checked = selected.has(type);
    const text = document.createElement('span');
    text.textContent = type;
    label.append(box, text);
    fragment.append(label);
  }
  container.querySelector('.type-filter-menu').replaceChildren(fragment);
  syncTypeFilterLabel(container, selected);
}

export function syncTypeFilterLabel(container, selected) {
  const label = container.querySelector('.type-filter-label');
  if (selected.size === 0) label.textContent = '全部类型';
  else if (selected.size === 1) label.textContent = [...selected][0];
  else label.textContent = `已选 ${selected.size} 项`;
}

export function renderTimeline(sections, items, filtered, sources = {}) {
  const groups = { done: [], running: [], pending: [] };
  for (const item of items) {
    if (groups[item.status]) groups[item.status].push(item);
  }
  const counts = {};
  for (const status of ['done', 'running', 'pending']) {
    counts[status] = renderSection(sections[status], groups[status], status, filtered, sources);
  }
  return counts;
}

function renderSection(section, items, status, filtered, sources) {
  section.count.textContent = String(items.length);
  if (!items.length) {
    renderEmpty(section.list, status, filtered, sources[sourceByStatus[status]]);
    return 0;
  }

  const existing = new Map([...section.list.querySelectorAll('.event-row')].map((node) => [node.dataset.id, node]));
  let reusableRunningNode = status === 'running' && items.length === 1 && existing.size === 1
    ? existing.values().next().value
    : null;
  let current = section.list.firstElementChild;
  for (const item of items) {
    const node = existing.get(item.id) || reusableRunningNode || createEventRow(item);
    const previousId = node.dataset.id;
    reusableRunningNode = null;
    updateEventRow(node, item);
    existing.delete(previousId);
    if (node === current) {
      current = current.nextElementSibling;
    } else {
      section.list.insertBefore(node, current);
    }
  }
  for (const node of existing.values()) node.remove();
  while (current) {
    const next = current.nextElementSibling;
    current.remove();
    current = next;
  }
  return items.length;
}

function renderEmpty(container, status, filtered, sourceStatus) {
  const empty = document.createElement('div');
  empty.className = `empty-state ${status}`;
  const title = document.createElement('strong');
  const unavailable = unavailableText[status]?.[sourceStatus];
  title.textContent = unavailable && !filtered ? unavailable : filtered ? emptyText[status][1] : emptyText[status][0];
  const detail = document.createElement('span');
  detail.textContent = unavailable && !filtered
    ? '请检查对应服务连接或状态上报'
    : status === 'running' ? 'Worker 空闲时这里保持为时间轴锚点' : '该存储层没有待展示的事件';
  empty.append(title, detail);
  container.replaceChildren(empty);
}

const unavailableText = {
  done: { unavailable: 'MongoDB 历史不可用' },
  running: { missing: 'Worker 尚未上报', unavailable: 'Worker 状态不可用', invalid: 'Worker 状态无效' },
  pending: { unavailable: 'Redis 队列不可用' },
};

function createEventRow(item) {
  const row = document.createElement('article');
  row.className = 'event-row';
  row.dataset.id = item.id;
  row.classList.add('enter');
  row.addEventListener('animationend', () => row.classList.remove('enter'), { once: true });
  row.innerHTML = `
    <div class="state-cell"><span class="status-dot"></span><div><strong></strong><small></small></div></div>
    <div class="event-main"><div class="event-title"><span class="event-type"></span></div><p class="event-preview"></p></div>
    <div class="source-cell"><strong></strong><small></small></div>
    <div class="row-actions"><button class="delete-button" type="button" aria-label="删除事件" title="删除事件"></button><button class="details-button" type="button" aria-label="展开事件详情" title="展开事件详情"></button></div>
    <div class="event-details"><pre></pre><textarea class="event-editor" spellcheck="false" hidden></textarea><div class="details-toolbar"><span class="edit-status"></span><button class="cancel-edit-button" type="button" hidden>取消</button><button class="edit-button" type="button">编辑</button></div></div>`;
  row.querySelector('.details-button').addEventListener('click', () => {
    const expanded = row.classList.toggle('expanded');
    const button = row.querySelector('.details-button');
    button.title = expanded ? '收起事件详情' : '展开事件详情';
    button.setAttribute('aria-label', button.title);
    if (row._item) {
      const key = itemKey(row._item);
      if (expanded) expandedKeys.add(key);
      else expandedKeys.delete(key);
    }
  });
  row.querySelector('.delete-button').addEventListener('click', () => {
    if (deleteHandler && row._item) deleteHandler(row._item);
  });
  row.querySelector('.event-editor').addEventListener('input', () => {
    row.classList.remove('edit-error');
    row.querySelector('.edit-status').textContent = '';
  });
  row.querySelector('.cancel-edit-button').addEventListener('click', () => cancelEventEdit(row));
  row.querySelector('.edit-button').addEventListener('click', () => toggleEventEdit(row));
  return row;
}

function cancelEventEdit(row) {
  const details = row.querySelector('pre');
  const editor = row.querySelector('.event-editor');
  row.classList.remove('editing');
  editor.value = '';
  editor.hidden = true;
  details.hidden = false;
  row.querySelector('.cancel-edit-button').hidden = true;
  row.querySelector('.edit-button').textContent = '编辑';
  row.querySelector('.edit-status').textContent = '';
  row.classList.remove('edit-error');
}

async function toggleEventEdit(row) {
  const button = row.querySelector('.edit-button');
  const cancelButton = row.querySelector('.cancel-edit-button');
  const status = row.querySelector('.edit-status');
  const details = row.querySelector('pre');
  const editor = row.querySelector('.event-editor');
  if (!row.classList.contains('editing')) {
    if (!row._item) return;
    editor.value = JSON.stringify(row._item.event, null, 2);
    editor.hidden = false;
    details.hidden = true;
    row.classList.add('editing');
    row.classList.remove('edit-error');
    button.textContent = '保存';
    cancelButton.hidden = false;
    status.textContent = '';
    editor.focus({ preventScroll: true });
    return;
  }
  if (!editHandler || !row._item) return;
  button.disabled = true;
  status.textContent = '保存中…';
  try {
    const result = await editHandler(row._item, editor.value);
    const event = result.event;
    row._item = { ...row._item, event };
    details.textContent = JSON.stringify(event, null, 2);
    row.classList.remove('editing');
    row.classList.remove('edit-error');
    editor.hidden = true;
    details.hidden = false;
    button.textContent = '编辑';
    cancelButton.hidden = true;
    status.textContent = result.updated ? '已保存' : '内容未改动';
  } catch (error) {
    row.classList.add('edit-error');
    status.textContent = error.message || '保存失败';
  } finally {
    button.disabled = false;
  }
}

function updateEventRow(row, item) {
  row._item = item;
  row.dataset.id = item.id;
  row.dataset.status = item.status;
  row.querySelector('.delete-button').hidden = item.status === 'running';
  row.querySelector('.edit-button').hidden = item.status === 'running';
  row.querySelector('.state-cell strong').textContent = statusText[item.status] || item.status;
  row.querySelector('.state-cell small').textContent = item.status === 'pending' ? `QUEUE ${item.position}` : item.status.toUpperCase();
  row.querySelector('.event-type').textContent = eventType(item);
  row.querySelector('.event-preview').textContent = eventPreview(item);
  row.querySelector('.source-cell strong').textContent = sourceText[item.source] || item.source;
  row.querySelector('.source-cell small').textContent = eventTime(item);
  if (row.classList.contains('editing')) return;
  const expanded = expandedKeys.has(itemKey(item));
  row.classList.toggle('expanded', expanded);
  const button = row.querySelector('.details-button');
  button.title = expanded ? '收起事件详情' : '展开事件详情';
  button.setAttribute('aria-label', button.title);
  const details = row.querySelector('pre');
  const content = JSON.stringify(item.event, null, 2);
  if (details.textContent !== content) {
    details.textContent = content;
  }
}