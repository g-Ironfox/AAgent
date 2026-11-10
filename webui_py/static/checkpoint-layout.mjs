// Arrange checkpoint ancestry from top to bottom, with siblings side by side.
export function layoutCheckpointTree(checkpoints) {
  const nodeWidth = 164, nodeHeight = 68, gap = 36, rowGap = 72, padding = 36;
  const byId = new Map(checkpoints.map(item => [item.seq, item]));
  const children = new Map([...byId.keys()].map(id => [id, []]));
  const roots = [];
  for (const item of byId.values()) {
    const parent = item.data?.parent_seq;
    if (parent == null || parent === 0) {
      roots.push(item.seq);
      continue;
    }
    if (!byId.has(parent) || parent >= item.seq) throw new Error('Checkpoint parent is invalid: #' + item.seq);
    children.get(parent).push(item.seq);
  }
  for (const list of children.values()) list.sort((a, b) => a - b);
  roots.sort((a, b) => a - b);

  const order = [], stack = [...roots].reverse();
  while (stack.length) {
    const id = stack.pop();
    order.push(id);
    stack.push(...children.get(id).reverse());
  }
  const widths = new Map();
  for (const id of [...order].reverse()) {
    const list = children.get(id);
    widths.set(id, Math.max(nodeWidth, list.reduce((sum, child) => sum + widths.get(child), 0) + Math.max(0, list.length - 1) * gap));
  }

  const positions = new Map(), pending = [];
  let rootLeft = padding;
  for (const id of roots) {
    pending.push({id, left: rootLeft, depth: 0});
    rootLeft += widths.get(id) + gap;
  }
  let height = checkpoints.length ? padding * 2 + nodeHeight : 0;
  while (pending.length) {
    const {id, left, depth} = pending.pop();
    const x = left + (widths.get(id) - nodeWidth) / 2;
    const y = padding + depth * (nodeHeight + rowGap);
    positions.set(id, {checkpoint: byId.get(id), x, y, width: nodeWidth, height: nodeHeight});
    height = Math.max(height, y + nodeHeight + padding);
    let childLeft = left;
    for (const child of children.get(id)) {
      pending.push({id: child, left: childLeft, depth: depth + 1});
      childLeft += widths.get(child) + gap;
    }
  }
  const edges = [];
  for (const [parent, list] of children) for (const child of list) edges.push({parent, child});
  return {nodes: [...positions.values()], edges, width: checkpoints.length ? rootLeft - gap + padding : 0, height};
}
