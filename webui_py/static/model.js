import { createModel, deleteModel, fetchModels, updateModel } from './api.js';

const state = { models: [], saving: false };
const elements = {
  form: document.querySelector('#modelForm'), id: document.querySelector('#modelId'), name: document.querySelector('#modelName'),
  provider: document.querySelector('#modelProvider'), model: document.querySelector('#modelModel'), baseUrl: document.querySelector('#modelBaseUrl'),
  apiKey: document.querySelector('#modelApiKey'), enabled: document.querySelector('#modelEnabled'), formTitle: document.querySelector('#formTitle'),
  formStatus: document.querySelector('#formStatus'), saveStatus: document.querySelector('#saveStatus'), items: document.querySelector('#modelItems'),
  count: document.querySelector('#listCount'), modelState: document.querySelector('#modelState'), newButton: document.querySelector('#newModelButton'),
};

function setStatus(message, error = false) { elements.saveStatus.textContent = message; elements.saveStatus.className = error ? 'error' : ''; }
function resetForm() { elements.form.reset(); elements.id.value = ''; elements.enabled.checked = true; elements.formTitle.textContent = '新建模型'; elements.formStatus.textContent = ''; setStatus(''); }
function formValue() { return { name: elements.name.value, provider: elements.provider.value, model: elements.model.value, base_url: elements.baseUrl.value, api_key: elements.apiKey.value, enabled: elements.enabled.checked }; }
function editModel(model) { elements.id.value = model.id; elements.name.value = model.name; elements.provider.value = model.provider; elements.model.value = model.model; elements.baseUrl.value = model.base_url; elements.apiKey.value = model.api_key; elements.enabled.checked = model.enabled; elements.formTitle.textContent = '编辑模型'; setStatus(''); elements.name.focus(); }

function render() {
  elements.count.textContent = `${state.models.length} 个配置`; elements.modelState.textContent = `${state.models.length} 个模型`;
  elements.items.replaceChildren();
  if (!state.models.length) { elements.items.innerHTML = '<p class="empty">还没有模型配置。</p>'; return; }
  state.models.forEach((model) => {
    const item = document.createElement('article'); item.className = `model-item${model.enabled ? '' : ' disabled'}`;
    item.innerHTML = `<div class="model-item-head"><strong></strong><span>${model.enabled ? '启用' : '停用'}</span></div><p></p><code></code><small>${model.api_key ? 'API Key 已配置' : '未配置 API Key'}</small><footer><button class="secondary-button edit" type="button">编辑</button><button class="delete-button" type="button">删除</button></footer>`;
    item.querySelector('strong').textContent = model.name; item.querySelector('p').textContent = `${model.provider} · ${model.model}`; item.querySelector('code').textContent = model.base_url;
    item.querySelector('.edit').addEventListener('click', () => editModel(model)); item.querySelector('.delete-button').addEventListener('click', () => removeModel(model)); elements.items.append(item);
  });
}

async function load() { try { const response = await fetchModels(); state.models = response.items; render(); } catch (error) { elements.modelState.textContent = '不可用'; setStatus(error.message, true); } }
async function removeModel(model) { if (!window.confirm(`确认删除“${model.name}”？`)) return; try { await deleteModel(model.id); if (elements.id.value === model.id) resetForm(); await load(); } catch (error) { setStatus(error.message, true); } }
elements.form.addEventListener('submit', async (event) => { event.preventDefault(); if (state.saving) return; state.saving = true; setStatus('保存中…'); try { const id = elements.id.value; if (id) await updateModel(id, formValue()); else await createModel(formValue()); resetForm(); await load(); setStatus('已保存'); } catch (error) { setStatus(error.message, true); } finally { state.saving = false; } });
elements.newButton.addEventListener('click', resetForm); load();