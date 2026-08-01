const FETCH_TIMEOUT_MS = 5000;

export async function fetchEvents(limit = 150) {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS);
  try {
    const response = await fetch(`/api/events?limit=${limit}`, { cache: 'no-store', signal: controller.signal });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(body.error || `HTTP ${response.status}`);
    return body;
  } finally {
    window.clearTimeout(timeout);
  }
}