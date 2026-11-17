const FETCH_TIMEOUT_MS = 5000;

async function request(path, options = {}) {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS);
  try {
    const response = await fetch(path, { cache: 'no-store', ...options, signal: controller.signal });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      const validationError = Array.isArray(body.detail)
        ? body.detail.map((item) => `${(item.loc || []).join('.')}: ${item.msg}`).join('; ')
        : '';
      throw new Error(body.error || validationError || `HTTP ${response.status}`);
    }
    return body;
  } finally {
    window.clearTimeout(timeout);
  }
}

export function fetchDocuments() {
  return request('/api/documents');
}

export function fetchSessions(cursor = '', query = '') {
  const params = new URLSearchParams({ limit: '50', q: query });
  if (cursor) params.set('cursor', cursor);
  return request(`/api/sessions?${params}`);
}

export function fetchSession(sessionId) {
  return request(`/api/sessions/${encodeURIComponent(sessionId)}`);
}

export function createSession(valueType, value) {
  return request('/api/sessions', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ value_type: valueType, value }),
  });
}

export function updateSession(sessionId, valueType, value, updatedAt) {
  return request(`/api/sessions/${encodeURIComponent(sessionId)}`, {
    method: 'PUT', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ value_type: valueType, value, updated_at: updatedAt }),
  });
}

export function deleteSession(sessionId) {
  return request(`/api/sessions/${encodeURIComponent(sessionId)}`, { method: 'DELETE' });
}

export function fetchDocument(documentId) {
  return request(`/api/documents/${encodeURIComponent(documentId)}`);
}

export function createDocument(title, content = '') {
  return request('/api/documents', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title, content }),
  });
}

export function updateDocument(documentId, title, content) {
  return request(`/api/documents/${encodeURIComponent(documentId)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title, content }),
  });
}

export function updateDocumentPin(documentId, pinned) {
  return request(`/api/documents/${encodeURIComponent(documentId)}/pin`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ pinned }),
  });
}

export function deleteDocument(documentId) {
  return request(`/api/documents/${encodeURIComponent(documentId)}`, { method: 'DELETE' });
}

export function fetchModels() {
  return request('/api/models');
}

export function fetchWorkflows() {
  return request('/api/workflows');
}

export function fetchWorkflow(name) {
  return request(`/api/workflow/${encodeURIComponent(name)}`);
}

export function renameWorkflow(currentName, name, workflowNodes = undefined) {
  return request(`/api/workflow/${encodeURIComponent(currentName)}/metadata`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, ...(workflowNodes ? { workflow_nodes: workflowNodes } : {}) }),
  });
}

export function deleteWorkflow(name) {
  return request(`/api/workflow/${encodeURIComponent(name)}`, { method: 'DELETE' });
}

export function createModel(model) {
  return request('/api/models', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(model),
  });
}

export function updateModel(modelId, model) {
  return request(`/api/models/${encodeURIComponent(modelId)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(model),
  });
}

export function deleteModel(modelId) {
  return request(`/api/models/${encodeURIComponent(modelId)}`, { method: 'DELETE' });
}

export function uploadWorkflow(name, workflow, overwrite = false) {
  return request(`/api/workflow/${encodeURIComponent(name)}`, {
    method: overwrite ? 'PUT' : 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(workflow),
  });
}

