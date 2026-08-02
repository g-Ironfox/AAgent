export function computeScrollTopForAnchor(previousScrollTop, previousAnchorOffset, nextAnchorOffset) {
  return previousScrollTop + (nextAnchorOffset - previousAnchorOffset);
}

export function captureAnchorState(container, selector = '.event-row') {
  if (!container) return null;

  const anchor = findAnchorElement(container, selector);
  const containerRect = typeof container.getBoundingClientRect === 'function' ? container.getBoundingClientRect() : { top: 0 };
  const anchorOffset = anchor && typeof anchor.getBoundingClientRect === 'function'
    ? anchor.getBoundingClientRect().top - containerRect.top
    : 0;

  return {
    anchorId: anchor?.dataset?.id ?? null,
    anchorOffset,
    scrollTop: container.scrollTop ?? 0,
  };
}

export function restoreAnchorState(container, state, selector = '.event-row') {
  if (!container || !state) return null;

  const anchor = state.anchorId
    ? container.querySelector?.(`[data-id="${CSS.escape(state.anchorId)}"]`)
    : null;

  if (!anchor) {
    const fallback = state.scrollTop ?? 0;
    container.scrollTop = fallback;
    return fallback;
  }

  const containerRect = typeof container.getBoundingClientRect === 'function' ? container.getBoundingClientRect() : { top: 0 };
  const nextAnchorOffset = anchor.getBoundingClientRect().top - containerRect.top;
  const nextScrollTop = computeScrollTopForAnchor(state.scrollTop, state.anchorOffset, nextAnchorOffset);
  container.scrollTop = nextScrollTop;
  return nextScrollTop;
}

function findAnchorElement(container, selector) {
  const rows = Array.from(container.querySelectorAll?.(selector) || []);
  if (!rows.length) return null;

  const containerRect = typeof container.getBoundingClientRect === 'function' ? container.getBoundingClientRect() : { top: 0 };
  let best = null;
  let bestDistance = Number.POSITIVE_INFINITY;

  for (const row of rows) {
    const rect = row.getBoundingClientRect();
    const distance = Math.abs(rect.top - containerRect.top);
    if (distance < bestDistance) {
      bestDistance = distance;
      best = row;
    }
  }

  return best;
}
