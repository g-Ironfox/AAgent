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

export function fetchEvents(limit = 150) {
  return request(`/api/events?limit=${limit}`);
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

export function fetchTerminalSessions() {
  return request('/api/terminal/sessions');
}

export function fetchTerminalHistory(limit = 150, terminalProcessId = '') {
  const params = new URLSearchParams({ limit: String(limit) });
  if (terminalProcessId) params.set('terminal_process_id', terminalProcessId);
  return request(`/api/terminal/history?${params}`);
}

export function submitTerminal(content, terminalProcessId = '') {
  return request('/api/terminal', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      content,
      files: [],
      ...(terminalProcessId ? { terminal_process_id: terminalProcessId } : {}),
    }),
  });
}

export function fetchEventBindings() {
  return request('/api/event-bindings');
}

export function fetchEventBindingWorkflowOptions() {
  return request('/api/event-bindings/workflow-options');
}

export function createEventBinding(binding) {
  return request('/api/event-bindings', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(binding),
  });
}

export function updateEventBinding(bindingId, binding) {
  return request(`/api/event-bindings/${encodeURIComponent(bindingId)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(binding),
  });
}

export function deleteEventBinding(bindingId) {
  return request(`/api/event-bindings/${encodeURIComponent(bindingId)}`, { method: 'DELETE' });
}

export function createProcess(workflowFileId, inputs) {
  return request('/api/processes', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ workflow_file_id: workflowFileId, inputs }),
  }, 30000);
}
