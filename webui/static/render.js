const statusText = { running: '进行中', pending: '将进行', done: '已处理' };
const sourceText = { worker: 'Worker', redis: 'Redis', mongodb: 'MongoDB' };

export function eventType(item) {
  return String(item.event?.event_type || '未分类');
}

export function eventPreview(item) {
  const payload = item.event?.payload;
  const candidates = [payload?.raw_message, payload?.result, payload?.message, payload?.tool, payload?.raw];
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

export function populateTypes(select, items) {
  const selected = select.value;
  const types = [...new Set(items.map(eventType))].sort((left, right) => left.localeCompare(right, 'zh-CN'));
  const fragment = document.createDocumentFragment();
  const all = document.createElement('option');
  all.value = 'all';
  all.textContent = '全部类型';
  fragment.append(all);
  for (const type of types) {
    const option = document.createElement('option');
    option.value = type;
    option.textContent = type;
    fragment.append(option);
  }
  select.replaceChildren(fragment);
  select.value = types.includes(selected) ? selected : 'all';
}

export function renderEvents(container, items) {
  if (!items.length) {
    const empty = document.createElement('div');
    empty.className = 'empty-state';
    const title = document.createElement('strong');
    title.textContent = '没有符合条件的事件';
    const detail = document.createElement('span');
    detail.textContent = '调整状态、类型或搜索条件';
    empty.append(title, detail);
    container.replaceChildren(empty);
    return;
  }

  const existing = new Map([...container.querySelectorAll('.event-row')].map((node) => [node.dataset.id, node]));
  const fragment = document.createDocumentFragment();
  for (const item of items) {
    const node = existing.get(item.id) || createEventRow(item);
    updateEventRow(node, item);
    fragment.append(node);
  }
  container.replaceChildren(fragment);
}

function createEventRow(item) {
  const row = document.createElement('article');
  row.className = 'event-row';
  row.dataset.id = item.id;
  row.classList.add('enter');
  row.addEventListener('animationend', () => row.classList.remove('enter'), { once: true });
  row.innerHTML = `
    <div class="state-cell"><span class="status-dot"></span><div><strong></strong><small></small></div></div>
    <div class="event-main"><div class="event-title"><span class="event-type"></span><span class="event-id"></span></div><p class="event-preview"></p></div>
    <div class="source-cell"><strong></strong><small></small></div>
    <button class="details-button" type="button" aria-label="展开事件详情" title="展开事件详情"></button>
    <div class="event-details"><pre></pre></div>`;
  row.querySelector('.details-button').addEventListener('click', () => {
    const expanded = row.classList.toggle('expanded');
    const button = row.querySelector('.details-button');
    button.title = expanded ? '收起事件详情' : '展开事件详情';
    button.setAttribute('aria-label', button.title);
  });
  return row;
}

function updateEventRow(row, item) {
  row.dataset.id = item.id;
  row.dataset.status = item.status;
  row.querySelector('.state-cell strong').textContent = statusText[item.status] || item.status;
  row.querySelector('.state-cell small').textContent = item.status === 'pending' ? `QUEUE ${item.position}` : item.status.toUpperCase();
  row.querySelector('.event-type').textContent = eventType(item);
  row.querySelector('.event-id').textContent = shortIdentifier(item);
  row.querySelector('.event-preview').textContent = eventPreview(item);
  row.querySelector('.source-cell strong').textContent = sourceText[item.source] || item.source;
  row.querySelector('.source-cell small').textContent = eventTime(item);
  row.querySelector('pre').textContent = JSON.stringify(item.event, null, 2);
}

function shortIdentifier(item) {
  const payload = item.event?.payload;
  const id = payload?.id || payload?.user_id || payload?.message_id;
  return id ? String(id) : item.id.slice(-10);
}