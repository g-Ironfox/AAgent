import { layoutCheckpointTree } from './checkpoint-layout.mjs';

const state = { checkpoints: [], layout: null, view: {scale: 1, x: 0, y: 0}, requestId: 0, headSeq: 0, selected: null, busy: false };
const el = Object.fromEntries([
  'eventCount', 'refreshButton', 'eventList', 'detailEyebrow', 'detailTitle', 'detailMeta',
  'detailSeq', 'checkoutButton', 'detailEmpty', 'diffList', 'pageStatus',
  'treeScene', 'zoomIn', 'zoomOut', 'zoomValue', 'fitTree',
].map((id) => [id, document.getElementById(id)]));

function setStatus(message, error = false) {
  el.pageStatus.textContent = message;
  el.pageStatus.classList.toggle('error', error);
}

function formatTime(value) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value || '未知时间' : new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium', timeStyle: 'short' }).format(date);
}

function applyViewport() {
  el.treeScene.style.transform = 'translate(' + state.view.x + 'px,' + state.view.y + 'px) scale(' + state.view.scale + ')';
  el.zoomValue.textContent = Math.round(state.view.scale * 100) + '%';
}

function fitTree() {
  if (!state.layout || !el.eventList.clientWidth || !el.eventList.clientHeight) return;
  const {width} = state.layout;
  const scale = Math.max(.15, Math.min(1, (el.eventList.clientWidth - 36) / width));
  state.view = {scale, x: (el.eventList.clientWidth - width * scale) / 2, y: 24};
  applyViewport();
}

function zoomTree(factor, x = el.eventList.clientWidth / 2, y = el.eventList.clientHeight / 2) {
  const previous = state.view.scale;
  const scale = Math.max(.15, Math.min(2, previous * factor));
  state.view.x = x - (x - state.view.x) * scale / previous;
  state.view.y = y - (y - state.view.y) * scale / previous;
  state.view.scale = scale;
  applyViewport();
}

function renderTree() {
  state.layout = layoutCheckpointTree(state.checkpoints);
  const positions = new Map(state.layout.nodes.map(node => [node.checkpoint.seq, node]));
  el.treeScene.replaceChildren();
  el.treeScene.style.width = state.layout.width + 'px';
  el.treeScene.style.height = state.layout.height + 'px';
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.classList.add('tree-edges');
  svg.setAttribute('width', state.layout.width);
  svg.setAttribute('height', state.layout.height);
  svg.setAttribute('aria-hidden', 'true');
  for (const edge of state.layout.edges) {
    const parent = positions.get(edge.parent), child = positions.get(edge.child);
    const line = document.createElementNS(svg.namespaceURI, 'line');
    line.setAttribute('x1', parent.x + parent.width / 2);
    line.setAttribute('y1', parent.y + parent.height);
    line.setAttribute('x2', child.x + child.width / 2);
    line.setAttribute('y2', child.y);
    svg.append(line);
  }
  el.treeScene.append(svg);
  for (const node of state.layout.nodes) {
    const checkpoint = node.checkpoint;
    const button = document.createElement('button');
    const isHead = checkpoint.seq === state.headSeq;
    button.type = 'button';
    button.className = 'graph-node' + (isHead ? ' is-head' : '') + (state.selected?.seq === checkpoint.seq ? ' selected' : '');
    button.style.left = node.x + 'px';
    button.style.top = node.y + 'px';
    button.style.width = node.width + 'px';
    button.style.height = node.height + 'px';
    button.setAttribute('aria-pressed', String(state.selected?.seq === checkpoint.seq));
    button.setAttribute('aria-current', isHead ? 'location' : 'false');
    button.setAttribute('aria-label', (checkpoint.data?.name || 'Checkpoint') + ' #' + checkpoint.seq + (isHead ? '，当前 HEAD' : ''));
    button.title = (checkpoint.data?.name || 'Checkpoint') + (checkpoint.seq ? ' · ' + formatTime(checkpoint.timestamp) : '');
    const title = document.createElement('strong');
    title.textContent = checkpoint.data?.name || 'Checkpoint';
    const meta = document.createElement('span');
    meta.className = 'graph-node-meta';
    const seq = document.createElement('small');
    const date = new Date(checkpoint.timestamp);
    const time = checkpoint.seq && !Number.isNaN(date.getTime())
      ? ' · ' + new Intl.DateTimeFormat('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }).format(date)
      : '';
    seq.textContent = '#' + checkpoint.seq + time;
    meta.append(seq);
    if (isHead) {
      const badge = document.createElement('small');
      badge.className = 'head-label';
      badge.textContent = 'HEAD';
      meta.append(badge);
    }
    button.append(title, meta);
    button.addEventListener('click', () => selectCheckpoint(checkpoint));
    el.treeScene.append(button);
  }
  el.eventCount.textContent = state.checkpoints.length + ' checkpoints';
  applyViewport();
}

async function selectCheckpoint(checkpoint) {
  const requestId = ++state.requestId;
  state.selected = checkpoint;
  renderTree();
  el.detailTitle.textContent = checkpoint.data?.name || 'Checkpoint';
  el.detailSeq.textContent = '#' + checkpoint.seq;
  el.detailEyebrow.textContent = 'CHECKPOINT DIFF';
  el.detailMeta.textContent = checkpoint.data?.parent_seq == null
    ? '根节点'
    : '父节点 #' + checkpoint.data.parent_seq + ' · ' + formatTime(checkpoint.timestamp);
  el.checkoutButton.disabled = state.busy || checkpoint.seq === state.headSeq;
  el.detailEmpty.hidden = true;
  el.diffList.hidden = false;
  el.diffList.replaceChildren();
  try {
    const response = await fetch('/api/files/checkpoints/' + checkpoint.seq + '/diff', { cache: 'no-store' });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(body.error || 'HTTP ' + response.status);
    if (requestId !== state.requestId) return;
    if (!body.changes.length) {
      const empty = document.createElement('p');
      empty.className = 'diff-empty';
      empty.textContent = checkpoint.data?.parent_seq == null ? '根节点没有文件差异' : '此 checkpoint 与父节点没有文件差异';
      el.diffList.append(empty);
    }
    for (const change of body.changes) {
      const section = document.createElement('section');
      section.className = 'file-diff';
      const heading = document.createElement('header');
      const fileName = document.createElement('strong');
      fileName.textContent = change.after_name || change.before_name || change.file_id;
      const badge = document.createElement('span');
      badge.className = 'diff-status ' + change.status;
      badge.textContent = change.status;
      heading.append(fileName, badge);
      section.append(heading);
      if (change.before_name && change.after_name && change.before_name !== change.after_name) {
        const rename = document.createElement('p');
        rename.className = 'rename-meta';
        rename.textContent = change.before_name + ' → ' + change.after_name;
        section.append(rename);
      }
      const pre = document.createElement('pre');
      pre.textContent = change.diff || '文件元数据有变化';
      section.append(pre);
      el.diffList.append(section);
    }
  } catch (error) {
    if (requestId === state.requestId) setStatus(error.message || '读取差异失败', true);
  }
}

async function loadTree() {
  state.busy = true;
  el.refreshButton.disabled = true;
  setStatus('正在读取 checkpoint 树…');
  try {
    const response = await fetch('/api/files/checkpoints/tree', { cache: 'no-store' });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(body.error || 'HTTP ' + response.status);
    state.checkpoints = body.items || [];
    state.headSeq = body.head_seq || 0;
    renderTree();
    fitTree();
    if (state.selected) {
      const selected = state.checkpoints.find((item) => item.seq === state.selected.seq);
      if (selected) await selectCheckpoint(selected);
    }
    setStatus('');
  } catch (error) {
    setStatus(error.message || '读取失败', true);
  } finally {
    state.busy = false;
    el.refreshButton.disabled = false;
    el.checkoutButton.disabled = !state.selected || state.selected.seq === state.headSeq;
  }
}

el.checkoutButton.addEventListener('click', async () => {
  if (!state.selected || state.busy || state.selected.seq === state.headSeq) return;
  if (!window.confirm('Checkout 到「' + (state.selected.data?.name || '初始工作区') + '」(#' + state.selected.seq + ')？当前工作区内容将被替换。')) return;
  state.busy = true;
  el.checkoutButton.disabled = true;
  try {
    const response = await fetch('/api/files/checkpoints/' + state.selected.seq + '/restore', { method: 'POST' });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(body.error || 'HTTP ' + response.status);
    await loadTree();
    setStatus('已 checkout 到 #' + body.data.checkpoint_seq);
  } catch (error) {
    setStatus(error.message || 'Checkout 失败', true);
  } finally {
    state.busy = false;
    el.checkoutButton.disabled = !state.selected || state.selected.seq === state.headSeq;
  }
});

el.zoomIn.addEventListener('click', () => zoomTree(1.25));
el.zoomOut.addEventListener('click', () => zoomTree(1 / 1.25));
el.fitTree.addEventListener('click', fitTree);
el.eventList.addEventListener('wheel', (event) => {
  event.preventDefault();
  const rect = el.eventList.getBoundingClientRect();
  zoomTree(Math.exp(-event.deltaY * .0015), event.clientX - rect.left, event.clientY - rect.top);
}, {passive: false});
let drag = null;
el.eventList.addEventListener('pointerdown', (event) => {
  if (event.button !== 0 || event.target.closest('button')) return;
  drag = {id: event.pointerId, x: event.clientX, y: event.clientY, originX: state.view.x, originY: state.view.y};
  el.eventList.setPointerCapture(event.pointerId);
  el.eventList.classList.add('dragging');
});
el.eventList.addEventListener('pointermove', (event) => {
  if (!drag || drag.id !== event.pointerId) return;
  state.view.x = drag.originX + event.clientX - drag.x;
  state.view.y = drag.originY + event.clientY - drag.y;
  applyViewport();
});
function endDrag() {
  drag = null;
  el.eventList.classList.remove('dragging');
}
el.eventList.addEventListener('pointerup', endDrag);
el.eventList.addEventListener('pointercancel', endDrag);
el.eventList.addEventListener('lostpointercapture', endDrag);
el.eventList.addEventListener('keydown', (event) => {
  if (event.target !== el.eventList) return;
  if (event.key === '+' || event.key === '=') zoomTree(1.25);
  else if (event.key === '-') zoomTree(1 / 1.25);
  else if (event.key === '0') fitTree();
  else return;
  event.preventDefault();
});
new ResizeObserver(() => { if (!drag) fitTree(); }).observe(el.eventList);
el.refreshButton.addEventListener('click', loadTree);
loadTree();
