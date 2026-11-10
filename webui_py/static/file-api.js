const timeoutMs = 8000;

async function request(path, options = {}) {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(path, { cache: 'no-store', ...options, signal: controller.signal });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      const details = Array.isArray(body.detail)
        ? body.detail.map((item) => item.msg).join('; ')
        : body.detail;
      throw new Error(body.error || details || 'HTTP ' + response.status);
    }
    return body;
  } finally {
    window.clearTimeout(timeout);
  }
}

export const fetchFiles = () => request('/api/files');
export const createCheckpoint = (name) => request('/api/files/checkpoints', {
  method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name }),
});
export const fetchFile = (id) => request('/api/files/' + encodeURIComponent(id));
export const createFile = (name, content = '') => request('/api/files', {
  method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name, content }),
});
export const updateFile = (id, name, content, revision) => request('/api/files/' + encodeURIComponent(id), {
  method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name, content, revision }),
});
export const updateFilePin = (id, pinned, revision) => request('/api/files/' + encodeURIComponent(id) + '/pin', {
  method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ pinned, revision }),
});
export const deleteFile = (id, revision) => request('/api/files/' + encodeURIComponent(id) + '?revision=' + revision, {
  method: 'DELETE',
});
