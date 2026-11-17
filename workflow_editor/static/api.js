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

export function fetchModels() {
  return request('/api/models');
}

export function fetchLocalTools() {
  return request('/api/tools/local');
}

export function fetchRemoteTools() {
  return request('/api/tools/remote');
}

