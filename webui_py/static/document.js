import { createDocument, deleteDocument, fetchDocument, fetchDocuments, updateDocument } from './api.js?v=documents-1';

const state = { documents: [], current: null, saved: null, loading: false, saving: false, mode: 'preview' };
const elements = {
  createButton: document.querySelector('#createButton'),
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

function formatDate(value) {
  if (!value) return '';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '' : `更新于 ${date.toLocaleString('zh-CN', { hour12: false })}`;
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
    const updated = document.createElement('small');
    updated.textContent = formatDate(documentItem.updated_at).replace('更新于 ', '');
    button.append(title, updated);
    button.addEventListener('click', () => selectDocument(documentItem.id));
    elements.documentList.append(button);
  }
}

function applyDocument(documentItem) {
  state.current = documentItem;
  state.saved = { title: documentItem.title, content: documentItem.content };
  elements.title.value = documentItem.title;
  elements.content.value = documentItem.content;
  elements.preview.textContent = documentItem.content;
  elements.updatedAt.textContent = formatDate(documentItem.updated_at);
  renderList();
  updateControls();
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
elements.editButton.addEventListener('click', () => {
  if (state.mode === 'edit') saveCurrentDocument();
  else startEditing();
});
elements.cancelButton.addEventListener('click', cancelEditing);
elements.deleteButton.addEventListener('click', removeCurrentDocument);
elements.title.addEventListener('input', () => { setStatus(''); updateControls(); });
elements.content.addEventListener('input', () => { elements.preview.textContent = elements.content.value; setStatus(''); updateControls(); });

loadDocuments();