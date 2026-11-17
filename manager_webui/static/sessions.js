import { createSession, deleteSession, fetchSession, fetchSessions, updateSession } from './api.js';

const elements = Object.fromEntries([
  'createButton', 'searchInput', 'searchButton', 'sessionList', 'listStatus', 'moreButton',
  'detailTitle', 'timestamp', 'copyButton', 'refreshButton', 'deleteButton', 'sessionForm',
  'valueType', 'valueInput', 'inputLabel', 'visualEditor', 'textEditor', 'editModes', 'visualButton',
  'jsonButton', 'formStatus', 'cancelButton', 'emptyDetail',
].map((id) => [id, document.getElementById(id)]));

let current = null;
let creating = false;
let nextCursor = null;
let query = '';
let listGeneration = 0;
let detailGeneration = 0;
let busy = false;
let draft = '';
let draftType = 'content';
let mode = 'visual';
let baseline = '';

const roles = ['system', 'user', 'assistant', 'tool'];
function initialValue(type) {
  if (type === 'number') return 0;
  if (type === 'content') return '';
  if (type === 'map-content') return {};
  if (type.startsWith('list-')) return [];
  if (type === 'message') return { role: 'user', content: '' };
  return { event_type: '', payload: {} };
}
function copy(value) { return JSON.parse(JSON.stringify(value)); }
function checkValue(type, value) {
  if (type === 'map-content') {
    if (!value || Array.isArray(value) || typeof value !== 'object' ||
        Object.entries(value).some(([key, item]) => !key || typeof item !== 'string')) {
      throw new Error('值必须是键非空、值为文本的 JSON 对象');
    }
    return;
  }
  const itemType = type.replace(/^list-/, '');
  if (type.startsWith('list-')) {
    if (!Array.isArray(value)) throw new Error('值必须是数组');
    value.forEach((item, index) => checkItem(itemType, item, `第 ${index} 项`));
  } else checkItem(itemType, value, '值');
}
function checkItem(type, value, label) {
  if (type === 'content') {
    if (typeof value !== 'string') throw new Error(`${label}必须是文本`);
  } else if (type === 'number') {
    if (typeof value !== 'number' || !Number.isFinite(value)) throw new Error(`${label}必须是有限数值`);
  } else if (type === 'message') {
    if (!value || Array.isArray(value) || typeof value !== 'object' ||
        Object.keys(value).sort().join(',') !== 'content,role' ||
        !roles.includes(value.role) || typeof value.content !== 'string') {
      throw new Error(`${label}必须包含合法 role 和文本 content，且不能有其他字段`);
    }
  } else if (!value || Array.isArray(value) || typeof value !== 'object' ||
             typeof value.event_type !== 'string' || !value.event_type ||
             !Object.hasOwn(value, 'payload')) {
    throw new Error(`${label}需要非空 event_type 和 payload`);
  }
}
function parseJson(text, label) {
  try { return JSON.parse(text); }
  catch { throw new Error(`${label}请输入有效的 JSON`); }
}
function field(label, value, name, multiline = false) {
  const wrapper = document.createElement('label');
  wrapper.textContent = label;
  const input = document.createElement(multiline ? 'textarea' : 'input');
  input.dataset.field = name;
  input.value = value;
  if (multiline) input.spellcheck = false;
  wrapper.append(input);
  return wrapper;
}
function itemEditor(type, value) {
  const editor = document.createElement('div');
  editor.className = 'item-fields';
  if (type === 'number') {
    const wrapper = field('数值', value, 'number');
    const input = wrapper.querySelector('input');
    input.type = 'number';
    input.step = 'any';
    editor.append(wrapper);
  }
  if (type === 'content') editor.append(field('内容', value, 'content', true));
  if (type === 'message') {
    const wrapper = document.createElement('label');
    wrapper.textContent = '角色';
    const select = document.createElement('select');
    select.dataset.field = 'role';
    for (const role of roles) {
      const option = document.createElement('option');
      option.value = option.textContent = role;
      select.append(option);
    }
    select.value = value.role;
    wrapper.append(select);
    editor.append(wrapper, field('内容', value.content, 'content', true));
  }
  if (type === 'event') {
    const extras = Object.fromEntries(Object.entries(value).filter(([key]) => !['event_type', 'payload'].includes(key)));
    editor.append(field('事件类型', value.event_type, 'event_type'),
      field('Payload (JSON)', JSON.stringify(value.payload, null, 2), 'payload', true),
      field('扩展字段 (JSON 对象)', JSON.stringify(extras, null, 2), 'extras', true));
  }
  return editor;
}
function readItem(type, editor, label) {
  const get = (name) => editor.querySelector(`[data-field="${name}"]`).value;
  if (type === 'number') return parseJson(get('number'), `${label}：`);
  if (type === 'content') return get('content');
  if (type === 'message') return { role: get('role'), content: get('content') };
  const payload = parseJson(get('payload'), `${label} payload：`);
  const extras = parseJson(get('extras'), `${label}扩展字段：`);
  if (!extras || Array.isArray(extras) || typeof extras !== 'object' ||
      Object.hasOwn(extras, 'event_type') || Object.hasOwn(extras, 'payload')) {
    throw new Error(`${label}扩展字段必须是对象，不能覆盖 event_type 或 payload`);
  }
  return { event_type: get('event_type'), payload, ...extras };
}
function readVisual() {
  if (draftType === 'map-content') {
    const entries = [...elements.visualEditor.querySelectorAll('.list-item')].map((row) => [
      row.querySelector('[data-field="key"]').value,
      row.querySelector('[data-field="value"]').value,
    ]);
    if (entries.some(([key]) => !key)) throw new Error('键不能为空');
    if (new Set(entries.map(([key]) => key)).size !== entries.length) throw new Error('键不能重复');
    return Object.fromEntries(entries);
  }
  const type = draftType.replace(/^list-/, '');
  if (draftType.startsWith('list-')) {
    return [...elements.visualEditor.querySelectorAll('.list-item')].map((row, index) =>
      readItem(type, row, `第 ${index} 项`));
  }
  return readItem(type, elements.visualEditor, '值');
}
function readDraft() {
  const value = draftType === 'content' ? elements.valueInput.value :
    mode === 'json' ? parseJson(elements.valueInput.value, '值：') : readVisual();
  checkValue(draftType, value);
  return value;
}
function dirty() {
  if (!current && !creating) return false;
  try {
    const value = draftType === 'content' ? elements.valueInput.value :
      mode === 'json' ? parseJson(elements.valueInput.value, '值：') : readVisual();
    return JSON.stringify(value) !== baseline;
  } catch { return true; }
}
function mayDiscard() { return !dirty() || window.confirm('有未保存的修改，确定丢弃吗？'); }
function renderEditor() {
  const type = draftType;
  elements.inputLabel.textContent = type === 'content' ? '文本' : 'JSON';
  elements.editModes.hidden = type === 'content';
  elements.visualButton.setAttribute('aria-pressed', String(mode === 'visual'));
  elements.jsonButton.setAttribute('aria-pressed', String(mode === 'json'));
  elements.textEditor.hidden = type !== 'content' && mode !== 'json';
  elements.visualEditor.hidden = type === 'content' || mode === 'json';
  if (type === 'content' || mode === 'json') {
    elements.valueInput.value = type === 'content' ? draft : JSON.stringify(draft, null, 2);
    return;
  }
  elements.visualEditor.replaceChildren();
  if (type === 'map-content') {
    const list = document.createElement('div');
    list.className = 'editor-list';
    for (const [key, value] of Object.entries(draft)) {
      list.append(mapRow(key, value));
    }
    const add = document.createElement('button');
    add.type = 'button';
    add.dataset.action = 'add';
    add.textContent = '+ 添加一项';
    elements.visualEditor.append(list, add);
    return;
  }
  if (!type.startsWith('list-')) {
    elements.visualEditor.append(itemEditor(type, draft));
    return;
  }
  const itemType = type.slice(5);
  const list = document.createElement('div');
  list.className = 'editor-list';
  for (const [index, value] of draft.entries()) {
    const row = document.createElement('section');
    row.className = 'list-item';
    const heading = document.createElement('div');
    heading.className = 'item-head';
    const title = document.createElement('strong');
    title.textContent = `#${index}  ${itemType === 'content' ? value.slice(0, 45) : itemType === 'message' ? value.role : value.event_type}`;
    const actions = document.createElement('div');
    for (const [text, action, unavailable] of [
      ['↑', 'up', index === 0], ['↓', 'down', index === draft.length - 1], ['删除', 'remove', false],
    ]) {
      const button = document.createElement('button');
      button.type = 'button';
      button.textContent = text;
      button.title = `${text}第 ${index} 项`;
      button.setAttribute('aria-label', button.title);
      button.dataset.action = action;
      if (unavailable) button.disabled = true;
      actions.append(button);
    }
    heading.append(title, actions);
    row.append(heading, itemEditor(itemType, value));
    list.append(row);
  }
  const add = document.createElement('button');
  add.type = 'button';
  add.dataset.action = 'add';
  add.textContent = '+ 添加一项';
  elements.visualEditor.append(list, add);
}
function mapRow(key, value) {
  const row = document.createElement('section');
  row.className = 'list-item map-item';
  const fields = document.createElement('div');
  fields.className = 'item-fields';
  fields.append(field('键', key, 'key'), field('内容', value, 'value', true));
  const remove = document.createElement('button');
  remove.type = 'button';
  remove.dataset.action = 'remove';
  remove.textContent = '删除';
  row.append(fields, remove);
  return row;
}
function setDraft(type, value) {
  draftType = type;
  draft = copy(value);
  baseline = JSON.stringify(value);
  mode = 'visual';
  renderEditor();
}

function report(message) { elements.formStatus.textContent = message; }
function setBusy(value) { busy = value; elements.sessionForm.dataset.busy = String(value); }
function formatDate(value) { return value ? new Date(value).toLocaleString('zh-CN') : ''; }
function updateSelection() {
  for (const button of elements.sessionList.querySelectorAll('[data-id]')) {
    button.classList.toggle('selected', button.dataset.id === current?.id && !creating);
  }
}
function showDetail() {
  elements.sessionForm.hidden = !current && !creating;
  elements.emptyDetail.hidden = Boolean(current || creating);
  elements.detailTitle.textContent = creating ? '新建 Session' : current?.id || '选择 Session';
  elements.timestamp.textContent = current ? `创建 ${formatDate(current.created_at)}  ·  更新 ${formatDate(current.updated_at)}` : '';
  elements.copyButton.disabled = !current || creating;
  elements.refreshButton.disabled = !current || creating;
  elements.deleteButton.disabled = !current || creating;
  elements.valueType.disabled = Boolean(current);
  updateSelection();
}
async function loadList(append = false) {
  const generation = ++listGeneration;
  const cursor = append ? nextCursor : '';
  if (append && !cursor) return;
  elements.listStatus.textContent = '读取中';
  elements.moreButton.hidden = true;
  try {
    const page = await fetchSessions(cursor, query);
    if (generation !== listGeneration) return;
    if (!append) elements.sessionList.replaceChildren();
    for (const item of page.items) {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'session-item';
      button.dataset.id = item.id;
      const title = document.createElement('strong');
      title.textContent = item.id;
      const meta = document.createElement('small');
      meta.textContent = `${item.value_type}  ·  ${formatDate(item.updated_at)}`;
      button.append(title, meta);
      button.addEventListener('click', () => openSession(item.id));
      elements.sessionList.append(button);
    }
    nextCursor = page.next_cursor;
    elements.moreButton.hidden = !nextCursor;
    elements.listStatus.textContent = `${elements.sessionList.children.length} 条${nextCursor ? '（更多可加载）' : ''}`;
    updateSelection();
  } catch (error) {
    if (generation === listGeneration) {
      elements.listStatus.textContent = error.message;
      elements.moreButton.hidden = !nextCursor;
    }
  }
}
async function openSession(id) {
  if (busy || !mayDiscard()) return;
  const generation = ++detailGeneration;
  elements.listStatus.textContent = '读取中';
  report('读取中');
  try {
    const document = await fetchSession(id);
    if (generation !== detailGeneration) return;
    current = document;
    creating = false;
    elements.valueType.value = document.value_type;
    setDraft(document.value_type, document.value);
    report('');
    showDetail();
    elements.listStatus.textContent = '';
  } catch (error) {
    if (generation === detailGeneration) { report(error.message); elements.listStatus.textContent = error.message; }
  }
}

elements.searchButton.addEventListener('click', () => {
  query = elements.searchInput.value.trim();
  nextCursor = null;
  loadList();
});
elements.searchInput.addEventListener('keydown', (event) => {
  if (event.key === 'Enter') { event.preventDefault(); elements.searchButton.click(); }
});
elements.moreButton.addEventListener('click', () => loadList(true));
elements.createButton.addEventListener('click', () => {
  if (busy || !mayDiscard()) return;
  ++detailGeneration;
  current = null;
  creating = true;
  elements.valueType.value = 'content';
  setDraft('content', '');
  report('');
  showDetail();
  elements.valueInput.focus();
});
elements.valueType.addEventListener('change', () => {
  const type = elements.valueType.value;
  if (dirty() && !window.confirm('切换类型会丢弃当前的值，确定继续吗？')) {
    elements.valueType.value = draftType;
    return;
  }
  setDraft(type, initialValue(type));
  report('');
});
elements.cancelButton.addEventListener('click', () => {
  if (busy || !mayDiscard()) return;
  if (creating) { creating = false; showDetail(); return; }
  if (current) setDraft(current.value_type, current.value);
  report('');
});
elements.jsonButton.addEventListener('click', () => {
  if (mode === 'json') return;
  try { draft = readVisual(); }
  catch (error) { report(error.message); return; }
  mode = 'json';
  renderEditor();
  report('');
});
elements.visualButton.addEventListener('click', () => {
  if (mode === 'visual') return;
  try { draft = readDraft(); }
  catch (error) { report(error.message); return; }
  mode = 'visual';
  renderEditor();
  report('');
});
elements.visualEditor.addEventListener('click', (event) => {
  const button = event.target.closest('button[data-action]');
  if (!button) return;
  const action = button.dataset.action;
  const row = button.closest('.list-item');
  if (draftType === 'map-content') {
    if (action === 'remove') row.remove();
    if (action === 'add') {
      const added = mapRow('', '');
      elements.visualEditor.querySelector('.editor-list').append(added);
      added.querySelector('[data-field="key"]').focus();
    }
    report('');
    return;
  }
  if (action === 'remove') row.remove();
  try { draft = readVisual(); }
  catch (error) { report(error.message); return; }
  const index = [...elements.visualEditor.querySelectorAll('.list-item')].indexOf(row);
  if (action === 'add') draft.push(initialValue(draftType.slice(5)));
  if (action === 'up' || action === 'down') {
    const other = index + (action === 'up' ? -1 : 1);
    [draft[index], draft[other]] = [draft[other], draft[index]];
  }
  renderEditor();
  report('');
});
elements.visualEditor.addEventListener('input', () => { report(''); });
elements.valueInput.addEventListener('input', () => { report(''); });
window.addEventListener('beforeunload', (event) => { if (dirty()) event.preventDefault(); });
elements.copyButton.addEventListener('click', async () => {
  if (!current) return;
  try { await navigator.clipboard.writeText(current.id); report('ID 已复制'); }
  catch { report('复制失败'); }
});
elements.refreshButton.addEventListener('click', () => { if (current && !busy) openSession(current.id); });
elements.deleteButton.addEventListener('click', async () => {
  if (!current || busy || !mayDiscard() || !window.confirm(`删除 Session ${current.id}？此操作不可撤销。`)) return;
  setBusy(true);
  try {
    await deleteSession(current.id);
    ++detailGeneration;
    current = null;
    report('');
    showDetail();
    await loadList();
  } catch (error) { report(error.message); }
  finally { setBusy(false); }
});
elements.sessionForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  if (busy) return;
  let value;
  try { value = readDraft(); }
  catch (error) { report(error.message); return; }
  setBusy(true);
  report('保存中');
  try {
    const document = creating
      ? await createSession(elements.valueType.value, value)
      : await updateSession(current.id, current.value_type, value, current.updated_at);
    current = document;
    creating = false;
    setDraft(document.value_type, document.value);
    showDetail();
    report('已保存');
    await loadList();
  } catch (error) { report(error.message); }
  finally { setBusy(false); }
});

showDetail();
loadList();