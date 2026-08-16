const FETCH_TIMEOUT_MS = 5000;

async function request(path, options = {}) {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS);
  try {
    const response = await fetch(path, { cache: 'no-store', ...options, signal: controller.signal });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(body.error || `HTTP ${response.status}`);
    return body;
  } finally {
    window.clearTimeout(timeout);
  }
}

export function fetchEvents(limit = 150) {
  return request(`/api/events?limit=${limit}`);
}

export function fetchSubagents() {
  return request('/api/subagents');
}

export function fetchSubagentEvents(agentId, limit = 150) {
  return request(`/api/subagents/${encodeURIComponent(agentId)}/events?limit=${limit}`);
}

export function fetchSubagentSettings(agentId) {
  return request(`/api/subagents/${encodeURIComponent(agentId)}/settings`);
}

export function updateSubagentSettings(agentId, documentIds) {
  return request(`/api/subagents/${encodeURIComponent(agentId)}/settings`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ document_ids: documentIds }),
  });
}

export function deleteEvent(payload) {
  return request('/api/events', {
    method: 'DELETE',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
}

export function updateEvent(payload) {
  return request('/api/events', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
}

export function fetchTerminalHistory(limit = 150) {
  return request(`/api/terminal/history?limit=${limit}`);
}

export function submitTerminal(message) {
  return request('/api/terminal', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, files: [] }),
  });
}

export function fetchSettings() {
  return request('/api/settings');
}

export function submitSystemPrompt(systemPrompt) {
  return request('/api/settings/system-prompt', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ system_prompt: systemPrompt }),
  });
}

export function fetchDocuments() {
  return request('/api/documents');
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

export function submitMaxContextCount(maxContextCount) {
  return request('/api/settings/max-context-count', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ max_context_count: maxContextCount }),
  });
}

export function fetchModels() {
  return request('/api/models');
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