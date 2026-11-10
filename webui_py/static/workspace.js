import {
  createFile,
  deleteFile,
  fetchFile,
  fetchFiles,
  updateFile,
  updateFilePin,
} from './file-api.js';

const state = { items: [], current: null, saved: null, mode: 'preview', busy: false };
const el = Object.fromEntries([
  'createButton', 'searchInput', 'fileList', 'fileCount', 'name', 'fileName',
  'fileContent', 'filePreview', 'fileEmpty', 'fileId', 'updatedAt',
  'pinButton', 'downloadButton', 'deleteButton', 'cancelButton', 'editButton',
  'saveStatus', 'characterCount',
].map((id) => [id, document.getElementById(id)]));
el.name = el.fileName;

function changed() {
  return Boolean(state.current && state.saved)
    && (el.name.value.trim() !== state.saved.name || el.fileContent.value !== state.saved.content);
}

function setStatus(text, kind = '') {
  el.saveStatus.textContent = text;
  el.saveStatus.className = 'save-status ' + kind;
}

function updateControls() {
  const active = Boolean(state.current);
  const busy = state.busy;
  const dirty = changed();
  el.name.disabled = !active || busy || state.mode !== 'edit';
  el.fileContent.disabled = !active || busy || state.mode !== 'edit';
  el.createButton.disabled = busy;
  el.pinButton.disabled = !active || busy || state.mode === 'edit';
  el.pinButton.textContent = state.current && state.current.pinned ? '已钉住' : '钉住';
  el.pinButton.setAttribute('aria-pressed', String(Boolean(state.current && state.current.pinned)));
  el.downloadButton.disabled = !active || busy;
  el.deleteButton.disabled = !active || busy;
  el.editButton.disabled = !active || busy || (state.mode === 'edit' && (!dirty || !el.name.value.trim()));
  el.editButton.textContent = state.mode === 'edit' ? '保存' : '编辑';
  el.cancelButton.hidden = state.mode !== 'edit';
  el.cancelButton.disabled = !active || busy;
  el.fileEmpty.hidden = active;
  el.filePreview.hidden = !active || state.mode !== 'preview';
  el.fileContent.hidden = !active || state.mode !== 'edit';
  el.characterCount.textContent = Array.from(el.fileContent.value).length + ' 字';
  renderList();
}

function renderList() {
  const query = el.searchInput.value.trim().toLocaleLowerCase();
  const visible = state.items.filter((item) => item.name.toLocaleLowerCase().includes(query));
  el.fileCount.textContent = state.items.length + ' 个文件';
  el.fileList.replaceChildren();
  if (!visible.length) {
    const empty = document.createElement('p');
    empty.className = 'list-empty';
    empty.textContent = state.items.length ? '没有匹配的文件' : '还没有文件';
    el.fileList.append(empty);
    return;
  }
  visible.forEach((item) => {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'file-item' + (item.file_id === (state.current && state.current.file_id) ? ' active' : '');
    const title = document.createElement('strong');
    title.textContent = item.name || '未命名文件';
    const meta = document.createElement('small');
    meta.className = item.pinned ? 'pinned' : '';
    meta.textContent = (item.pinned ? '已钉住 · ' : '') + formatDate(item.updated_at);
    button.append(title, meta);
    button.addEventListener('click', () => selectFile(item.file_id));
    el.fileList.append(button);
  });
}

function formatDate(value) {
  if (!value) return '尚未更新';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '' : date.toLocaleString('zh-CN', { hour12: false });
}

function applyFile(item) {
  state.current = item;
  state.saved = { name: item.name, content: item.content };
  el.name.value = item.name;
  el.fileContent.value = item.content;
  el.filePreview.textContent = item.content;
  el.fileId.textContent = item.file_id;
  el.updatedAt.textContent = '更新于 ' + formatDate(item.updated_at);
  updateControls();
}

async function loadFiles() {
  state.busy = true;
  setStatus('正在读取…');
  updateControls();
  try {
    const result = await fetchFiles();
    state.items = result.items;
    if (state.current) {
      const refreshed = await fetchFile(state.current.file_id);
      applyFile(refreshed);
    } else if (state.items.length) {
      applyFile(await fetchFile(state.items[0].file_id));
    }
    setStatus('已同步', 'success');
  } catch (error) {
    setStatus(error.message || '读取失败', 'error');
  } finally {
    state.busy = false;
    updateControls();
  }
}

async function selectFile(id) {
  if (state.busy || (state.current && id === state.current.file_id)) return;
  if (changed() && !window.confirm('当前修改尚未保存，仍要切换文件吗？')) return;
  state.busy = true;
  updateControls();
  try {
    state.mode = 'preview';
    applyFile(await fetchFile(id));
    setStatus('已同步', 'success');
  } catch (error) {
    setStatus(error.message, 'error');
  } finally {
    state.busy = false;
    updateControls();
  }
}

async function createNew() {
  if (state.busy) return;
  if (changed() && !window.confirm('当前修改尚未保存，仍要新建文件吗？')) return;
  state.busy = true;
  setStatus('正在新建…');
  updateControls();
  try {
    const item = await createFile('未命名文件');
    state.items.unshift(item);
    state.mode = 'edit';
    applyFile(item);
    setStatus('已创建', 'success');
    el.name.focus();
    el.name.select();
  } catch (error) {
    setStatus(error.message, 'error');
  } finally {
    state.busy = false;
    updateControls();
  }
}

async function saveCurrent() {
  if (!state.current || state.busy || !changed() || !el.name.value.trim()) return;
  state.busy = true;
  setStatus('正在保存…');
  updateControls();
  try {
    const saved = await updateFile(state.current.file_id, el.name.value.trim(), el.fileContent.value, state.current.revision);
    state.mode = 'preview';
    const index = state.items.findIndex((item) => item.file_id === saved.file_id);
    if (index >= 0) state.items[index] = saved;
    applyFile(saved);
    setStatus('已保存', 'success');
  } catch (error) {
    setStatus(error.message, 'error');
  } finally {
    state.busy = false;
    updateControls();
  }
}

async function togglePin() {
  if (!state.current || state.busy) return;
  state.busy = true;
  updateControls();
  try {
    const updated = await updateFilePin(state.current.file_id, !state.current.pinned, state.current.revision);
    const index = state.items.findIndex((item) => item.file_id === updated.file_id);
    if (index >= 0) state.items[index] = updated;
    applyFile(updated);
    setStatus(updated.pinned ? '已钉住' : '已取消钉住', 'success');
  } catch (error) {
    setStatus(error.message, 'error');
  } finally {
    state.busy = false;
    updateControls();
  }
}

async function removeCurrent() {
  if (!state.current || state.busy || !window.confirm('确定删除“' + state.current.name + '”吗？')) return;
  state.busy = true;
  updateControls();
  try {
    await deleteFile(state.current.file_id, state.current.revision);
    state.items = state.items.filter((item) => item.file_id !== state.current.file_id);
    state.current = null;
    state.saved = null;
    state.mode = 'preview';
    el.name.value = '';
    el.fileContent.value = '';
    el.filePreview.textContent = '';
    el.fileId.textContent = '';
    el.updatedAt.textContent = '';
    if (state.items.length) applyFile(await fetchFile(state.items[0].file_id));
    setStatus('已删除', 'success');
  } catch (error) {
    setStatus(error.message, 'error');
  } finally {
    state.busy = false;
    updateControls();
  }
}

el.createButton.addEventListener('click', createNew);
el.searchInput.addEventListener('input', renderList);
el.editButton.addEventListener('click', () => {
  if (state.mode === 'edit') saveCurrent();
  else { state.mode = 'edit'; setStatus(''); updateControls(); }
});
el.cancelButton.addEventListener('click', () => {
  if (!state.saved) return;
  el.name.value = state.saved.name;
  el.fileContent.value = state.saved.content;
  el.filePreview.textContent = state.saved.content;
  state.mode = 'preview';
  setStatus('');
  updateControls();
});
el.pinButton.addEventListener('click', togglePin);
el.deleteButton.addEventListener('click', removeCurrent);
el.downloadButton.addEventListener('click', () => {
  if (!state.current) return;
  const blob = new Blob([state.current.content], { type: 'text/markdown;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = (state.current.name || 'file') + '.md';
  link.click();
  URL.revokeObjectURL(url);
});
el.name.addEventListener('input', () => { setStatus(''); updateControls(); });
el.fileContent.addEventListener('input', () => {
  el.filePreview.textContent = el.fileContent.value;
  setStatus('');
  updateControls();
});
document.addEventListener('keydown', (event) => {
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's' && state.mode === 'edit') {
    event.preventDefault();
    saveCurrent();
  }
});

loadFiles();
