import { createDocument, deleteDocument, fetchDocument, fetchDocuments, updateDocument, updateDocumentPin } from './api.js?v=documents-3';

const state = { documents: [], current: null, saved: null, loading: false, saving: false, mode: 'preview' };
const elements = {
  createButton: document.querySelector('#createButton'),
  uploadButton: document.querySelector('#uploadButton'),
  uploadInput: document.querySelector('#uploadInput'),
  downloadButton: document.querySelector('#downloadButton'),
  pinButton: document.querySelector('#pinButton'),
  editButton: document.querySelector('#editButton'),
  cancelButton: document.querySelector('#cancelButton'),
  deleteButton: document.querySelector('#deleteButton'),
  documentList: document.querySelector('#documentList'),
  title: document.querySelector('#documentTitle'),
  content: document.querySelector('#documentContent'),
  preview: document.querySelector('#documentPreview'),
  empty: document.querySelector('#documentEmpty'),
  documentState: document.querySelector('#documentState'),
  saveStatus: document.querySelector('#saveStatus'),
  characterCount: document.querySelector('#characterCount'),
  updatedAt: document.querySelector('#updatedAt'),
};

function setStatus(message, type = '') {
  elements.saveStatus.className = `save-status ${type}`.trim();
  elements.saveStatus.textContent = message;
}

function formatDate(value, label = '更新于') {
  if (!value) return '';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '' : `${label} ${date.toLocaleString('zh-CN', { hour12: false })}`;
}

function currentInput() {
  return { title: elements.title.value.trim(), content: elements.content.value };
}

function isChanged() {
  const input = currentInput();
  return Boolean(state.saved) && (input.title !== state.saved.title || input.content !== state.saved.content);
}

function updateControls() {
  const active = Boolean(state.current);
  const busy = state.loading || state.saving;
  const changed = isChanged();
  elements.title.disabled = !active || busy || state.mode !== 'edit';
  elements.content.disabled = !active || busy || state.mode !== 'edit';
  elements.createButton.disabled = busy;
  elements.uploadButton.disabled = busy;
  elements.downloadButton.disabled = !active || busy;
  elements.pinButton.disabled = !active || busy;
  elements.pinButton.textContent = state.current?.pinned ? '已钉住' : '钉住';
  elements.pinButton.classList.toggle('pinned', Boolean(state.current?.pinned));
  elements.pinButton.setAttribute('aria-pressed', String(Boolean(state.current?.pinned)));
  elements.editButton.textContent = state.mode === 'edit' ? '保存' : '编辑';
  elements.editButton.classList.toggle('save-button', state.mode === 'edit');
  elements.editButton.disabled = !active || busy || (state.mode === 'edit' && (!changed || !elements.title.value.trim()));
  elements.cancelButton.disabled = !active || busy || state.mode !== 'edit';
  elements.cancelButton.hidden = state.mode !== 'edit';
  elements.deleteButton.disabled = !active || busy;
  elements.characterCount.textContent = `${[...elements.content.value].length} 字`;
  elements.empty.hidden = active;
  elements.preview.hidden = !active || state.mode !== 'preview';
  elements.content.hidden = !active || state.mode !== 'edit';
}

function markdownTitle(fileName) {
  const title = fileName.replace(/\.(md|txt)$/i, '').trim() || '未命名文档';
  return [...title].slice(0, 200).join('');
}

function validateMarkdownFile(file) {
  if (!/\.(md|txt)$/i.test(file.name)) throw new Error(`“${file.name}”不是 .md 或 .txt 文件`);
}

async function importMarkdownFiles(fileList, selectImported) {
  const files = [...fileList];
  if (!files.length || state.loading || state.saving) return;
  if (selectImported && isChanged() && !window.confirm('当前修改尚未保存，仍要上传并打开新文档吗？')) return;

  state.saving = true;
  setStatus(files.length === 1 ? '正在上传…' : `正在导入 0/${files.length}…`);
  updateControls();
  const imported = [];
  const failures = [];
  for (const [index, file] of files.entries()) {
    try {
      validateMarkdownFile(file);
      const content = await file.text();
      if ([...content].length > 1_000_000) throw new Error('正文超过 100 万字符');
      imported.push(await createDocument(markdownTitle(file.name), content));
    } catch (error) {
      failures.push(`${file.name}: ${error.message}`);
    }
    if (files.length > 1) setStatus(`正在导入 ${index + 1}/${files.length}…`);
  }

  state.documents.unshift(...imported.reverse());
  if (selectImported && imported.length) {
    state.mode = 'preview';
    applyDocument(imported[imported.length - 1]);
  } else {
    renderList();
  }
  state.saving = false;
  elements.documentState.textContent = failures.length ? '部分同步' : '已同步';
  if (failures.length) {
    setStatus(`已导入 ${imported.length} 个，失败 ${failures.length} 个：${failures.join('；')}`, 'error');
  } else {
    setStatus(files.length === 1 ? '上传完成' : `已导入 ${imported.length} 个文档`, 'success');
  }
  updateControls();
}

function downloadCurrentDocument() {
  if (!state.current || state.loading || state.saving) return;
  const content = state.mode === 'edit' ? elements.content.value : state.current.content;
  const safeTitle = (elements.title.value.trim() || state.current.title || '未命名文档')
    .replace(/[<>:"/\\|?*\u0000-\u001f]/g, '_')
    .replace(/[. ]+$/g, '') || '未命名文档';
  const url = URL.createObjectURL(new Blob([content], { type: 'text/markdown;charset=utf-8' }));
  const link = document.createElement('a');
  link.href = url;
  link.download = `${safeTitle}.md`;
  link.click();
  URL.revokeObjectURL(url);
  setStatus('下载已开始', 'success');
}

function renderList() {
  elements.documentList.replaceChildren();
  if (!state.documents.length) {
    const empty = document.createElement('p');
    empty.className = 'list-empty';
    empty.textContent = '还没有文档';
    elements.documentList.append(empty);
    return;
  }
  for (const documentItem of state.documents) {
    const button = document.createElement('button');
    button.className = `document-item${documentItem.id === state.current?.id ? ' active' : ''}`;
    button.type = 'button';
    const title = document.createElement('strong');
    title.textContent = documentItem.title;
    if (documentItem.pinned) {
      const pin = document.createElement('span');
      pin.className = 'document-pin';
      pin.textContent = '钉住';
      title.append(' ', pin);
    }
    const updated = document.createElement('small');
    updated.textContent = formatDate(documentItem.updated_at);
    button.append(title, updated);
    button.addEventListener('click', () => selectDocument(documentItem.id));
    elements.documentList.append(button);
  }
}

function applyDocument(documentItem) {
  state.current = documentItem;
  elements.title.value = documentItem.title;
  elements.content.value = documentItem.content;
  state.saved = currentInput();
  elements.preview.textContent = documentItem.content;
  elements.updatedAt.textContent = formatDate(documentItem.created_at, '创建于');
  renderList();
  updateControls();
}

async function togglePin() {
  if (!state.current || state.loading || state.saving) return;
  state.saving = true;
  setStatus('正在更新钉住状态…');
  updateControls();
  try {
    const documentItem = await updateDocumentPin(state.current.id, !state.current.pinned);
    state.current = { ...state.current, pinned: documentItem.pinned };
    const index = state.documents.findIndex((item) => item.id === documentItem.id);
    if (index >= 0) state.documents[index] = { ...state.documents[index], pinned: documentItem.pinned };
    renderList();
    elements.documentState.textContent = '已同步';
    setStatus(documentItem.pinned ? '文档已钉住' : '已取消钉住', 'success');
  } catch (error) {
    setStatus(error.name === 'AbortError' ? '更新超时，请重试' : error.message, 'error');
  } finally {
    state.saving = false;
    updateControls();
  }
}

async function loadDocuments() {
  state.loading = true;
  elements.documentState.textContent = '读取中';
  updateControls();
  try {
    const response = await fetchDocuments();
    state.documents = response.items;
    renderList();
    elements.documentState.textContent = '已同步';
  } catch (error) {
    elements.documentState.textContent = '不可用';
    setStatus(error.name === 'AbortError' ? '读取超时，请重试' : error.message, 'error');
  } finally {
    state.loading = false;
    updateControls();
  }
}

async function selectDocument(documentId) {
  if (state.loading || state.saving || documentId === state.current?.id) return;
  if (isChanged() && !window.confirm('当前修改尚未保存，仍要切换文档吗？')) return;
  state.loading = true;
  setStatus('');
  updateControls();
  try {
    state.mode = 'preview';
    applyDocument(await fetchDocument(documentId));
    elements.documentState.textContent = '已同步';
  } catch (error) {
    setStatus(error.name === 'AbortError' ? '读取超时，请重试' : error.message, 'error');
  } finally {
    state.loading = false;
    updateControls();
  }
}

async function createNewDocument() {
  if (state.loading || state.saving) return;
  if (isChanged() && !window.confirm('当前修改尚未保存，仍要新建文档吗？')) return;
  state.saving = true;
  setStatus('正在新建…');
  updateControls();
  let created = false;
  try {
    const documentItem = await createDocument('未命名文档');
    state.documents.unshift(documentItem);
    state.mode = 'edit';
    applyDocument(documentItem);
    elements.documentState.textContent = '已同步';
    setStatus('已创建', 'success');
    created = true;
  } catch (error) {
    setStatus(error.name === 'AbortError' ? '新建超时，请重试' : error.message, 'error');
  } finally {
    state.saving = false;
    updateControls();
    if (created) {
      elements.title.focus();
      elements.title.select();
    }
  }
}

async function saveCurrentDocument() {
  const input = currentInput();
  if (!state.current || !input.title || state.saving) return;
  state.saving = true;
  setStatus('正在保存…');
  updateControls();
  try {
    const documentItem = await updateDocument(state.current.id, input.title, input.content);
    const index = state.documents.findIndex((item) => item.id === documentItem.id);
    if (index >= 0) state.documents[index] = documentItem;
    else state.documents.unshift(documentItem);
    state.mode = 'preview';
    applyDocument(documentItem);
    elements.documentState.textContent = '已同步';
    setStatus('已保存', 'success');
  } catch (error) {
    setStatus(error.name === 'AbortError' ? '保存超时，请重试' : error.message, 'error');
  } finally {
    state.saving = false;
    updateControls();
  }
}

function startEditing() {
  if (!state.current || state.loading || state.saving) return;
  state.mode = 'edit';
  setStatus('');
  updateControls();
}

function cancelEditing() {
  if (!state.current || state.loading || state.saving || state.mode !== 'edit') return;
  elements.title.value = state.saved.title;
  elements.content.value = state.saved.content;
  elements.preview.textContent = state.saved.content;
  state.mode = 'preview';
  setStatus('');
  updateControls();
}

async function removeCurrentDocument() {
  if (!state.current || state.saving || !window.confirm(`确定删除“${state.current.title}”吗？`)) return;
  state.saving = true;
  setStatus('正在删除…');
  updateControls();
  try {
    await deleteDocument(state.current.id);
    state.documents = state.documents.filter((item) => item.id !== state.current.id);
    state.current = null;
    state.saved = null;
    state.mode = 'preview';
    elements.title.value = '';
    elements.content.value = '';
    elements.preview.textContent = '';
    elements.updatedAt.textContent = '';
    renderList();
    elements.documentState.textContent = '已同步';
    setStatus('已删除', 'success');
  } catch (error) {
    setStatus(error.name === 'AbortError' ? '删除超时，请重试' : error.message, 'error');
  } finally {
    state.saving = false;
    updateControls();
  }
}

elements.createButton.addEventListener('click', createNewDocument);
elements.uploadButton.addEventListener('click', () => elements.uploadInput.click());
elements.downloadButton.addEventListener('click', downloadCurrentDocument);
elements.pinButton.addEventListener('click', togglePin);
elements.uploadInput.addEventListener('change', async () => {
  await importMarkdownFiles(elements.uploadInput.files, elements.uploadInput.files.length === 1);
  elements.uploadInput.value = '';
});
elements.editButton.addEventListener('click', () => {
  if (state.mode === 'edit') saveCurrentDocument();
  else startEditing();
});
elements.cancelButton.addEventListener('click', cancelEditing);
elements.deleteButton.addEventListener('click', removeCurrentDocument);
elements.title.addEventListener('input', () => { setStatus(''); updateControls(); });
elements.content.addEventListener('input', () => { elements.preview.textContent = elements.content.value; setStatus(''); updateControls(); });

loadDocuments();