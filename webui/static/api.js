export async function fetchEvents(limit = 150) {
  const response = await fetch(`/api/events?limit=${limit}`, { cache: 'no-store' });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.error || `HTTP ${response.status}`);
  return body;
}