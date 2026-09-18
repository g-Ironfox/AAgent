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