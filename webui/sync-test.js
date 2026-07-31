// 仿真 syncList 算法(不依赖真实 DOM),验证节点复用与顺序正确性。
function makeSyncList({ itemKeyByNode }) {
  return function syncList(container, items, keyOf, createNode, updateNode) {
    const buckets = new Map();
    for (const child of container.children) {
      const key = itemKeyByNode.get(child);
      if (key == null) continue;
      const bucket = buckets.get(key);
      if (bucket) bucket.push(child);
      else buckets.set(key, [child]);
    }
    const used = new Set();
    let anchor = null;
    for (let i = items.length - 1; i >= 0; i--) {
      const item = items[i];
      const key = keyOf(item);
      const bucket = buckets.get(key);
      const node = bucket && bucket.length ? bucket.shift() : null;
      if (node) {
        updateNode(node, item);
      } else {
        const fresh = createNode(item);
        itemKeyByNode.set(fresh, key);
        used.add(fresh);
        if (fresh.nextSibling !== anchor) container.insertBefore(fresh, anchor);
        anchor = fresh;
        continue;
      }
      used.add(node);
      if (node.nextSibling !== anchor) container.insertBefore(node, anchor);
      anchor = node;
    }
    for (const child of [...container.children]) {
      if (!used.has(child)) child.remove();
    }
  };
}

// ---- 极简 DOM 仿真 ----
function makeNode(id, content) {
  return {
    id, content, nextSibling: null, previousSibling: null, parent: null,
    data: null, // 记录 updateNode 最近写入的内容
  };
}
function makeContainer() {
  const c = { children: [], insertBefore(node, anchor) {
    if (node.parent) this.remove(node);
    node.parent = c;
    const at = anchor ? c.children.indexOf(anchor) : c.children.length;
    if (at < 0) throw new Error('anchor not in container');
    c.children.splice(at, 0, node);
    c.reindex();
  }, remove(node) {
    const i = c.children.indexOf(node);
    if (i >= 0) { c.children.splice(i, 1); node.parent = null; c.reindex(); }
  }, reindex() {
    for (let i = 0; i < c.children.length; i++) {
      c.children[i].previousSibling = c.children[i - 1] || null;
      c.children[i].nextSibling = c.children[i + 1] || null;
    }
  } };
  return c;
}

const itemKeyByNode = new WeakMap();
const syncList = makeSyncList({ itemKeyByNode });

let seq = 0;
function createNode(item) {
  const n = makeNode(`n${++seq}`, item);
  n.data = item;
  return n;
}
function updateNode(node, item) { node.data = item; }

const keyOf = (item) => String(item); // 用内容做 key,模拟重复内容场景
const show = (c) => c.children.map((n) => n.id + ':' + n.data).join(' ');

function check(name, actual, expected) {
  const ok = actual === expected;
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}`);
  if (!ok) console.log(`   got:      ${actual}\n   expected: ${expected}`);
  return ok;
}

let pass = true;
const all = [];
const run = (name, f) => { try { const r = f(); all.push(check(name, r.actual, r.expected)); } catch (e) { all.push(false); console.log(`FAIL ${name}: ${e.message}`); } };

// 1. 首次渲染
run('初始渲染', () => {
  const c = makeContainer();
  syncList(c, ['A', 'B', 'C'], keyOf, createNode, updateNode);
  return { actual: show(c), expected: 'n1:A n2:B n3:C' };
});

// 2. 新条目插到顶部(历史新增) -> 只创建 1 个新节点
run('顶部新增', () => {
  const c = makeContainer();
  syncList(c, ['A', 'B', 'C'], keyOf, createNode, updateNode);
  const before = seq;
  syncList(c, ['D', 'A', 'B', 'C'], keyOf, createNode, updateNode);
  return { actual: show(c), expected: `n${before + 1}:D n1:A n2:B n3:C` };
});

// 3. 顶部消费(队列 BRPOP) -> 复用全部幸存节点,不新建
run('顶部移除', () => {
  const c = makeContainer();
  syncList(c, ['A', 'B', 'C'], keyOf, createNode, updateNode);
  const before = seq;
  syncList(c, ['B', 'C'], keyOf, createNode, updateNode);
  return { actual: show(c), expected: `n2:B n3:C` + (seq > before ? ' (不应新建节点!)' : '') };
});

// 4. 底部新增(LPUSH 溢出/窗口滑动) + 底部移除
run('底部新增并移除', () => {
  const c = makeContainer();
  syncList(c, ['A', 'B', 'C'], keyOf, createNode, updateNode);
  syncList(c, ['D', 'A', 'B'], keyOf, createNode, updateNode); // C 被挤出,顶部加 D
  return { actual: show(c), expected: 'n5:D n1:A n2:B' };
});

// 5. 重复内容条目(两条相同 raw)不会折叠
run('重复内容保留两条', () => {
  const c = makeContainer();
  syncList(c, ['X', 'Y', 'X'], keyOf, createNode, updateNode);
  const before = seq;
  syncList(c, ['Y', 'X', 'Z', 'X'], keyOf, createNode, updateNode);
  return { actual: show(c), expected: `n6:Y n7:X n8:Z n3:X` + (seq > before + 2 ? ' (新建过多!)' : '') };
});

// 6. 全部清空 -> 节点全部移除
run('清空列表', () => {
  const c = makeContainer();
  syncList(c, ['A', 'B'], keyOf, createNode, updateNode);
  syncList(c, [], keyOf, createNode, updateNode);
  return { actual: show(c), expected: '' };
});

// 7. 展开状态保留:复用节点必须是同一个对象
run('复用节点保留展开态', () => {
  const c = makeContainer();
  syncList(c, ['A', 'B', 'C'], keyOf, createNode, updateNode);
  const nodeB = c.children[1];
  syncList(c, ['A', 'B', 'C', 'D'], keyOf, createNode, updateNode);
  return { actual: c.children[1] === nodeB ? 'same-node' : 'rebuilt!', expected: 'same-node' };
});

console.log('\n' + (all.every(Boolean) ? '全部通过 ✓' : `有 ${all.filter(Boolean).length}/${all.length} 通过,存在失败 ✗`));
