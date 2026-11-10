const pageSize = 50;
const state = { events: [], beforeSeq: null, hasMore: false, busy: false, selected: null, fileId: '' };
const el = Object.fromEntries([
  'eventCount', 'refreshButton', 'filterForm', 'fileFilter', 'eventList', 'loadMoreButton',
  'detailEyebrow', 'detailTitle', 'detailSeq', 'detailEmpty', 'detailBody', 'detailFileId',
  'detailTimestamp', 'detailEventId', 'contentSection', 'detailContent', 'detailPayload', 'pageStatus',
].map((id) => [id, document.getElementById(id)]));

const eventLabels = {
  'file.create': '新建文件',
  'file.update': '编辑文件',
  'file.pin': '修改置顶状态',
  'file.delete': '删除文件',
};

function setStatus(message, error = false) {
  el.pageStatus.textContent = message;
  el.pageStatus.classList.toggle('error', error);
}

function formatTime(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value || '未知时间';
  return new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium', timeStyle: 'medium' }).format(date);
}

function eventName(event) {
  return event.data?.name || event.data?.title || event.file_id || '未知文件';
}

function renderList() {
  el.eventList.replaceChildren();
  if (!state.events.length) {
    const empty = document.createElement('p');
    empty.className = 'event-list-empty';
    empty.textContent = state.fileId ? '没有匹配的修改记录' : '还没有修改记录';
    el.eventList.append(empty);
  }

  for (const event of state.events) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'event-item' + (state.selected?.seq === event.seq ? ' active' : '');
    button.setAttribute('aria-current', String(state.selected?.seq === event.seq));
    const top = document.createElement('span');
    top.className = 'event-item-top';
    const action = document.createElement('strong');
    action.textContent = eventLabels[event.type] || event.type;
    const seq = document.createElement('code');
    seq.textContent = '#' + event.seq;
    top.append(action, seq);
    const name = document.createElement('span');
    name.className = 'event-item-name';
    name.textContent = eventName(event);
    const time = document.createElement('time');
    time.dateTime = event.timestamp || '';
    time.textContent = formatTime(event.timestamp);
    button.append(top, name, time);
    button.addEventListener('click', () => selectEvent(event));
    el.eventList.append(button);
  }
  el.eventCount.textContent = String(state.events.length) + (state.hasMore ? '+' : '');
  el.loadMoreButton.hidden = !state.hasMore;
  el.loadMoreButton.disabled = state.busy;
  el.refreshButton.disabled = state.busy;
}

function selectEvent(event) {
  state.selected = event;
  el.detailEyebrow.textContent = eventLabels[event.type] || event.type;
  el.detailTitle.textContent = eventName(event);
  el.detailSeq.textContent = '#' + event.seq;
  el.detailFileId.textContent = event.file_id || '';
  el.detailTimestamp.textContent = formatTime(event.timestamp);
  el.detailEventId.textContent = event.event_id || '';
  const data = event.data || {};
  const hasContent = typeof data.content === 'string';
  el.contentSection.hidden = !hasContent;
  el.detailContent.textContent = hasContent ? data.content : '';
  const payload = { ...data };
  delete payload.content;
  el.detailPayload.textContent = JSON.stringify(payload, null, 2) || '{}';
  el.detailEmpty.hidden = true;
  el.detailBody.hidden = false;
  renderList();
}

async function loadEvents({ append = false } = {}) {
  if (state.busy) return;
  state.busy = true;
  renderList();
  setStatus('正在读取事件…');
  const params = new URLSearchParams({ limit: String(pageSize) });
  if (append && state.beforeSeq !== null) params.set('before_seq', String(state.beforeSeq));
  if (state.fileId) params.set('file_id', state.fileId);
  try {
    const response = await fetch('/api/files/events?' + params, { cache: 'no-store' });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(body.error || body.detail || 'HTTP ' + response.status);
    state.events = append ? [...state.events, ...body.items] : body.items;
    state.hasMore = body.has_more;
    state.beforeSeq = body.next_before_seq;
    if (state.selected && !state.events.some((event) => event.seq === state.selected.seq)) {
      state.selected = null;
      el.detailBody.hidden = true;
      el.detailEmpty.hidden = false;
      el.detailTitle.textContent = '选择一条修改记录';
      el.detailSeq.textContent = '';
    }
    if (state.selected) {
      const selected = state.events.find((event) => event.seq === state.selected.seq);
      if (selected) selectEvent(selected);
    }
    setStatus('');
  } catch (error) {
    setStatus(error.message || '读取失败', true);
  } finally {
    state.busy = false;
    renderList();
  }
}

el.refreshButton.addEventListener('click', () => loadEvents());
el.loadMoreButton.addEventListener('click', () => loadEvents({ append: true }));
el.filterForm.addEventListener('submit', (event) => {
  event.preventDefault();
  state.fileId = el.fileFilter.value.trim();
  state.selected = null;
  el.detailBody.hidden = true;
  el.detailEmpty.hidden = false;
  loadEvents();
});

loadEvents();
