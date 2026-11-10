const pageSize = 50;
const state = {
  checkpoints: [], beforeSeq: null, hasMore: false, busy: false,
  selectedCheckpoint: null, selectedFile: null, expanded: new Set(), fileId: '',
};
const el = Object.fromEntries([
  'eventCount', 'refreshButton', 'filterForm', 'fileFilter', 'eventList', 'loadMoreButton',
  'detailEyebrow', 'detailTitle', 'detailSeq', 'detailEmpty', 'detailBody', 'detailFileId',
  'detailTimestamp', 'detailEventId', 'contentSection', 'contentHeading', 'detailContent', 'detailPayload', 'pageStatus',
].map((id) => [id, document.getElementById(id)]));

function setStatus(message, error = false) {
  el.pageStatus.textContent = message;
  el.pageStatus.classList.toggle('error', error);
}

function formatTime(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value || '未知时间';
  return new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium', timeStyle: 'medium' }).format(date);
}

function renderList() {
  el.eventList.replaceChildren();
  if (!state.checkpoints.length) {
    const empty = document.createElement('p');
    empty.className = 'event-list-empty';
    empty.textContent = state.fileId ? '没有包含该文件的 checkpoint' : '还没有 checkpoint';
    el.eventList.append(empty);
  }

  state.checkpoints.forEach((checkpoint, index) => {
    const group = document.createElement('section');
    const expanded = state.expanded.has(checkpoint.seq);
    group.className = 'checkpoint-group'
      + (index === state.checkpoints.length - 1 && !state.hasMore ? ' last' : '')
      + (expanded ? ' expanded' : '');
    const row = document.createElement('button');
    row.type = 'button';
    row.className = 'checkpoint-row' + (state.selectedCheckpoint?.seq === checkpoint.seq && !state.selectedFile ? ' active' : '');
    row.setAttribute('aria-expanded', String(state.expanded.has(checkpoint.seq)));
    row.setAttribute('aria-label', (state.expanded.has(checkpoint.seq) ? '收起' : '展开') + ' ' + (checkpoint.data?.name || 'checkpoint'));
    const graph = document.createElement('span');
    graph.className = 'checkpoint-graph';
    graph.setAttribute('aria-hidden', 'true');
    const node = document.createElement('span');
    node.className = 'checkpoint-node';
    graph.append(node);
    const chevron = document.createElement('span');
    chevron.className = 'checkpoint-chevron' + (state.expanded.has(checkpoint.seq) ? ' expanded' : '');
    chevron.textContent = '›';
    const summary = document.createElement('span');
    summary.className = 'checkpoint-summary';
    const title = document.createElement('strong');
    title.textContent = checkpoint.data?.name || 'Checkpoint';
    const seq = document.createElement('code');
    seq.textContent = '#' + checkpoint.seq;
    const meta = document.createElement('span');
    meta.className = 'checkpoint-meta';
    const fileCount = Array.isArray(checkpoint.data?.files) ? checkpoint.data.files.length : 0;
    meta.textContent = fileCount + ' 个文件 · ' + formatTime(checkpoint.timestamp);
    const titleLine = document.createElement('span');
    titleLine.className = 'checkpoint-title-line';
    titleLine.append(title, seq);
    summary.append(titleLine, meta);
    row.append(graph, summary, chevron);
    row.addEventListener('click', () => {
      if (state.expanded.has(checkpoint.seq)) state.expanded.delete(checkpoint.seq);
      else state.expanded.add(checkpoint.seq);
      selectCheckpoint(checkpoint);
    });
    group.append(row);

    if (expanded) {
      const files = document.createElement('div');
      files.className = 'checkpoint-files';
      const snapshot = Array.isArray(checkpoint.data?.files) ? checkpoint.data.files : [];
      if (!snapshot.length) {
        const empty = document.createElement('p');
        empty.className = 'snapshot-empty';
        empty.textContent = '空工作区';
        files.append(empty);
      }
      for (const file of snapshot) {
        const fileButton = document.createElement('button');
        fileButton.type = 'button';
        fileButton.className = 'snapshot-file' + (state.selectedCheckpoint?.seq === checkpoint.seq && state.selectedFile?.file_id === file.file_id ? ' active' : '');
        const fileName = document.createElement('span');
        fileName.className = 'snapshot-file-name';
        fileName.textContent = file.name || '未命名文件';
        const fileRevision = document.createElement('code');
        fileRevision.textContent = '#' + file.revision;
        fileButton.append(fileName, fileRevision);
        fileButton.addEventListener('click', () => selectSnapshotFile(checkpoint, file));
        files.append(fileButton);
      }
      group.append(files);
    }
    el.eventList.append(group);
  });

  el.eventCount.textContent = String(state.checkpoints.length) + (state.hasMore ? '+' : '');
  el.loadMoreButton.hidden = !state.hasMore;
  el.loadMoreButton.disabled = state.busy;
  el.refreshButton.disabled = state.busy;
}

function showDetail(title, eyebrow, seq, fileId, timestamp, eventId, contentTitle, content, payload) {
  el.detailEyebrow.textContent = eyebrow;
  el.detailTitle.textContent = title;
  el.detailSeq.textContent = seq ? '#' + seq : '';
  el.detailFileId.textContent = fileId || '';
  el.detailTimestamp.textContent = formatTime(timestamp);
  el.detailEventId.textContent = eventId || '';
  el.contentSection.hidden = content === null;
  el.contentHeading.textContent = contentTitle || '';
  el.detailContent.textContent = content || '';
  el.detailPayload.textContent = JSON.stringify(payload || {}, null, 2);
  el.detailEmpty.hidden = true;
  el.detailBody.hidden = false;
}

function selectCheckpoint(checkpoint) {
  state.selectedCheckpoint = checkpoint;
  state.selectedFile = null;
  const files = checkpoint.data?.files || [];
  showDetail(
    checkpoint.data?.name || 'Checkpoint', 'CHECKPOINT', checkpoint.seq, '', checkpoint.timestamp,
    checkpoint.event_id, '快照内容', null,
    { 文件数: files.length, 文件: files.map((file) => file.name) },
  );
  renderList();
}

function selectSnapshotFile(checkpoint, file) {
  state.selectedCheckpoint = checkpoint;
  state.selectedFile = file;
  showDetail(
    file.name || '未命名文件', 'CHECKPOINT FILE', checkpoint.seq, file.file_id,
    checkpoint.timestamp, checkpoint.event_id, 'Checkpoint 时的文件内容', file.content || '',
    { revision: file.revision, pinned: Boolean(file.pinned), updated_at: file.updated_at },
  );
  renderList();
}

async function loadCheckpoints({ append = false } = {}) {
  if (state.busy) return;
  state.busy = true;
  renderList();
  setStatus('正在读取 checkpoint…');
  const params = new URLSearchParams({ limit: String(pageSize) });
  if (append && state.beforeSeq !== null) params.set('before_seq', String(state.beforeSeq));
  if (state.fileId) params.set('file_id', state.fileId);
  try {
    const response = await fetch('/api/files/checkpoints?' + params, { cache: 'no-store' });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(body.error || body.detail || 'HTTP ' + response.status);
    state.checkpoints = append ? [...state.checkpoints, ...body.items] : body.items;
    state.hasMore = body.has_more;
    state.beforeSeq = body.next_before_seq;
    const selected = state.checkpoints.find((item) => item.seq === state.selectedCheckpoint?.seq);
    if (selected) {
      state.selectedCheckpoint = selected;
      if (state.selectedFile) {
        const file = (selected.data?.files || []).find((item) => item.file_id === state.selectedFile.file_id);
        state.selectedFile = file || null;
      }
    } else if (state.selectedCheckpoint) {
      state.selectedCheckpoint = null;
      state.selectedFile = null;
      el.detailBody.hidden = true;
      el.detailEmpty.hidden = false;
      el.detailTitle.textContent = '选择一个 checkpoint';
    }
    if (state.selectedFile) selectSnapshotFile(state.selectedCheckpoint, state.selectedFile);
    else if (state.selectedCheckpoint) selectCheckpoint(state.selectedCheckpoint);
    setStatus('');
  } catch (error) {
    setStatus(error.message || '读取失败', true);
  } finally {
    state.busy = false;
    renderList();
  }
}

el.refreshButton.addEventListener('click', () => loadCheckpoints());
el.loadMoreButton.addEventListener('click', () => loadCheckpoints({ append: true }));
el.filterForm.addEventListener('submit', (event) => {
  event.preventDefault();
  state.fileId = el.fileFilter.value.trim();
  state.selectedCheckpoint = null;
  state.selectedFile = null;
  state.expanded.clear();
  el.detailBody.hidden = true;
  el.detailEmpty.hidden = false;
  loadCheckpoints();
});

loadCheckpoints();
