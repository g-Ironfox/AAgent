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