const FETCH_TIMEOUT_MS = 5000;

async function request(path, options = {}, timeoutMs = FETCH_TIMEOUT_MS) {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), timeoutMs);
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

export function fetchTerminalSessions() {
  return request('/api/terminal/sessions');
}

export function fetchTerminalHistory(limit, terminalId) {
  const params = new URLSearchParams({ limit: String(limit) });
  params.set('terminal_id', terminalId);
  return request(`/api/terminal/history?${params}`);
}

export function submitTerminal(content, terminalId) {
  return request('/api/terminal', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      content,
      files: [],
      terminal_id: terminalId,
    }),
  });
}

export function fetchProcessWorkflowOptions() {
  return request('/api/processes/workflow-options');
}

export function createProcess(workflowFileId, terminalId, inputs) {
  return request('/api/processes', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ workflow_file_id: workflowFileId, terminal_id: terminalId, inputs }),
  }, 30000);
}
