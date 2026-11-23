import assert from 'node:assert/strict';
import { test } from 'node:test';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { compileLifecycles, lifecycleFingerprint } from './static/workflow/domain/lifecycle.js';
import { createLifecyclePreview } from './static/workflow/domain/lifecycle-preview.js';

const node = (id, type = 'construct_content', extra = {}) => ({ id, type, name: id, ...extra });
const control = (fromId, toId, fromPortId = 'control-out', toPortId = 'control-in') => ({ fromId, fromPortId, toId, toPortId, type: 'control' });
const data = (fromId, toId, fromPortId = 'content-out', toPortId = 'content-in') => ({ fromId, fromPortId, toId, toPortId, type: 'content' });
const tree = () => ({
  nodes: [node('i', 'input'), node('r', 'router', { branches: [{ id: 'a', name: 'A' }] }), node('a'), node('b'), node('oa', 'output'), node('ob', 'output')],
  connections: [control('i', 'r'), control('r', 'a', 'a'), control('r', 'b', 'branch$others'), control('a', 'oa'), control('b', 'ob')],
});
const loop = () => ({
  nodes: [node('i', 'input'), node('f', 'foreach', { item_type: 'content' }), node('body'), node('o', 'output')],
  connections: [control('i', 'f'), control('f', 'body', 'loop-out'), control('body', 'f', 'control-out', 'loop-in'), control('f', 'o')],
});
const messages = (result) => result.errors.map((error) => error.message).join('\n');

test('linear tree uses only root; compile is repeatable and does not mutate nodes', () => {
  const graph = { nodes: [node('i', 'input'), node('o', 'output')], connections: [control('i', 'o')] };
  const before = structuredClone(graph);
  const first = compileLifecycles(graph);
  assert.equal(first.scopes.length, 1);
  assert.equal(first.nodeScopes.get('o'), 'L0');
  assert.deepEqual(first.errors, []);
  assert.deepEqual(graph, before);
  assert.deepEqual(compileLifecycles(graph), first);
});

test('router creates sibling child scopes and accepts ancestor input', () => {
  const graph = tree();
  graph.connections.push(data('i', 'a'), data('i', 'b'), data('a', 'oa'));
  const result = compileLifecycles(graph);
  assert.deepEqual(result.errors, []);
  assert.equal(result.scopes.length, 3);
  assert.equal(result.nodeScopes.get('r'), 'L0');
  assert.notEqual(result.nodeScopes.get('a'), result.nodeScopes.get('b'));
  assert.equal(result.nodeScopes.get('a'), result.nodeScopes.get('oa'));
  assert.deepEqual(result.scopes.slice(1).map((scope) => scope.parentId), ['L0', 'L0']);
});

test('data between sibling branches is rejected and highlighted', () => {
  const graph = tree();
  const edge = data('a', 'b');
  graph.connections.push(edge);
  const result = compileLifecycles(graph);
  assert.equal(result.structureValid, true);
  assert.equal(result.errors.length, 1);
  assert.match(messages(result), /数据越界/);
  assert.ok(result.invalidConnections.has(edge));
});

test('branch merges are rejected even when an Output is the shared node', () => {
  const graph = tree();
  graph.nodes = graph.nodes.filter((item) => item.id !== 'ob');
  graph.connections.find((edge) => edge.fromId === 'b').toId = 'oa';
  const result = compileLifecycles(graph);
  assert.equal(result.structureValid, false);
  assert.match(messages(result), /不允许分支汇合/);
});

test('ordinary cycles, duplicate control outputs, and disconnected drafts fail', () => {
  const graph = tree();
  graph.connections.push(control('a', 'r'));
  graph.nodes.push(node('stray'));
  const result = compileLifecycles(graph);
  assert.equal(result.structureValid, false);
  assert.match(messages(result), /多个后继/);
  assert.match(messages(result), /无法从 Input 到达/);
  const cycle = { nodes: [node('i', 'input'), node('a'), node('b')], connections: [control('i', 'a'), control('a', 'b'), control('b', 'a')] };
  assert.match(messages(compileLifecycles(cycle)), /形成了非 Foreach/);
});

test('foreach body is child; continuation and list input remain in parent', () => {
  const graph = loop();
  graph.connections.push(data('i', 'f', 'list', 'list-in'), data('i', 'body'), data('f', 'body', 'item-out'));
  const result = compileLifecycles(graph);
  assert.deepEqual(result.errors, []);
  assert.equal(result.scopes.length, 2);
  assert.equal(result.nodeScopes.get('f'), 'L0');
  assert.equal(result.nodeScopes.get('o'), 'L0');
  assert.equal(result.scopes[1].parentId, 'L0');
  assert.equal(result.outputScopes.get('f')['item-out'], result.nodeScopes.get('body'));
});

test('both foreach item-out and body values cannot leak outside', () => {
  const graph = loop();
  graph.connections.push(data('body', 'o'), data('f', 'o', 'item-out', 'item'));
  const result = compileLifecycles(graph);
  assert.equal(result.structureValid, true);
  assert.equal(result.errors.length, 2);
  assert.equal(result.invalidConnections.size, 2);
});

test('empty loop body returning directly to loop-in is supported', () => {
  const graph = loop();
  graph.nodes = graph.nodes.filter((item) => item.id !== 'body');
  graph.connections = [control('i', 'f'), control('f', 'f', 'loop-out', 'loop-in'), control('f', 'o')];
  assert.deepEqual(compileLifecycles(graph).errors, []);
});

test('unclosed loop, outside entry to loop-in, and branches in body fail', () => {
  const graph = loop();
  graph.connections = graph.connections.filter((edge) => edge.toPortId !== 'loop-in');
  assert.match(messages(compileLifecycles(graph)), /缺少循环体返回/);
  const outside = loop();
  outside.connections[0].toPortId = 'loop-in';
  assert.match(messages(compileLifecycles(outside)), /只能接收自己循环体/);
  const branched = loop();
  Object.assign(branched.nodes.find((item) => item.id === 'body'), { type: 'router', branches: [] });
  branched.connections.find((edge) => edge.fromId === 'body').fromPortId = 'branch$others';
  assert.match(messages(compileLifecycles(branched)), /循环体内不允许多分支节点/);
});

test('foreach inside a branch inherits the branch parent, not root', () => {
  const graph = tree();
  Object.assign(graph.nodes.find((item) => item.id === 'a'), { type: 'foreach', item_type: 'content' });
  graph.nodes.push(node('body'));
  graph.connections.push(control('a', 'body', 'loop-out'), control('body', 'a', 'control-out', 'loop-in'), data('i', 'body'), data('a', 'body', 'item-out'));
  const result = compileLifecycles(graph);
  assert.deepEqual(result.errors, []);
  const bodyScope = result.scopes.find((scope) => scope.id === result.nodeScopes.get('body'));
  assert.equal(bodyScope.parentId, result.nodeScopes.get('a'));
  assert.equal(bodyScope.depth, 2);
});

test('nested routers inherit branch scope and cannot access cousins', () => {
  const graph = tree();
  Object.assign(graph.nodes.find((item) => item.id === 'a'), { type: 'router', branches: [] });
  graph.connections.find((edge) => edge.fromId === 'a').fromPortId = 'branch$others';
  const result = compileLifecycles(graph);
  assert.deepEqual(result.errors, []);
  assert.equal(result.scopes.find((scope) => scope.id === result.nodeScopes.get('oa')).parentId, result.nodeScopes.get('a'));
  graph.connections.push(data('b', 'oa'));
  assert.match(messages(compileLifecycles(graph)), /数据越界/);
});

test('branch-local data cannot feed a boundary input in its parent', () => {
  const graph = tree();
  graph.connections.push(data('a', 'r'));
  assert.match(messages(compileLifecycles(graph)), /数据越界/);
});

test('json_tool success/error outputs belong to their own child scopes', () => {
  const graph = tree();
  graph.nodes[1].type = 'json_tool';
  graph.connections[1].fromPortId = 'control-out';
  graph.connections[2].fromPortId = 'error-out';
  graph.connections.push(data('r', 'a', 'result-json'), data('r', 'b', 'error-json'));
  assert.deepEqual(compileLifecycles(graph).errors, []);
  graph.connections.push(data('r', 'b', 'result-json', 'wrong'));
  assert.match(messages(compileLifecycles(graph)), /数据越界/);
});

test('missing optional json_tool error-out does not fail the preview', () => {
  const graph = { nodes: [node('i', 'input'), node('j', 'json_tool'), node('o', 'output')], connections: [control('i', 'j'), control('j', 'o')] };
  assert.deepEqual(compileLifecycles(graph).errors, []);
});

test('serialized node arguments are supported; positions do not affect fingerprint', () => {
  const graph = tree();
  graph.nodes[1].arguments = { branches: graph.nodes[1].branches };
  delete graph.nodes[1].branches;
  assert.deepEqual(compileLifecycles(graph).errors, []);
  const fingerprint = lifecycleFingerprint(graph);
  graph.nodes[0].x = 900;
  graph.nodes[0].y = 300;
  assert.equal(lifecycleFingerprint(graph), fingerprint);
  graph.connections.pop();
  assert.notEqual(lifecycleFingerprint(graph), fingerprint);
});

// DOM contract smoke test without an external browser/package dependency.
function fakeDOM() {
  const rules = [];
  const sheet = { cssRules: rules, insertRule(selector, index) {
    rules.splice(index, 0, { style: { setProperty() {}, set cssText(_) {} } });
    return index;
  } };
  const element = () => ({
    dataset: {}, children: [], hidden: false, textContent: '', title: '',
    classList: { add() {}, remove() {}, toggle() {} },
    append(...items) { this.children.push(...items); },
    replaceChildren(...items) { this.children = items; },
    setAttribute(key, value) { this[key] = value; },
    querySelectorAll() { return this.ports || []; },
  });
  return { element, document: { styleSheets: [sheet], querySelectorAll: () => [{ href: '/css/workflow.css', sheet }], createElement: element, createElementNS: element } };
}

test('preview renders legend, parent labels, boundary ports, errors, invalidation and clear', () => {
  const oldDocument = globalThis.document;
  const dom = fakeDOM();
  globalThis.document = dom.document;
  try {
    const graph = loop();
    const elements = Object.fromEntries(['compileLifecyclesButton', 'lifecyclePanel', 'lifecycleSummary', 'lifecycleScopes', 'lifecycleErrors'].map((id) => [id, dom.element()]));
    const preview = createLifecyclePreview(elements, graph);
    preview.compile();
    assert.match(elements.lifecycleSummary.textContent, /2 个生命周期/);
    assert.equal(elements.lifecycleScopes.children.length, 2);
    assert.match(elements.lifecycleScopes.children[1].textContent, /L0 → L1/);
    const rendered = dom.element();
    rendered.ports = ['list-in', 'item-out', 'loop-in'].map((id) => {
      const port = dom.element();
      port.dataset = { portId: id, portDirection: id === 'item-out' ? 'output' : 'input' };
      return port;
    });
    preview.decorateNode(rendered, graph.nodes[1]);
    assert.equal(rendered.dataset.lifecycleId, 'L0');
    assert.equal(rendered.children[0].textContent, 'L0 → L1');
    assert.deepEqual(rendered.ports.map((port) => port.dataset.lifecycleId), ['L0', 'L1', 'L1']);
    graph.nodes[1].x = 20;
    assert.equal(preview.invalidate(), false);
    graph.connections = structuredClone(graph.connections);
    assert.equal(preview.invalidate(), true, 'reimported objects must invalidate old connection identities');
    preview.compile();
    const edge = data('body', 'o');
    graph.connections.push(edge);
    assert.equal(preview.invalidate(), true);
    assert.match(elements.lifecycleSummary.textContent, /请重新编译/);
    assert.equal(elements.lifecycleScopes.children.length, 0);
    preview.compile();
    assert.match(elements.lifecycleSummary.textContent, /1 条数据越界/);
    const path = dom.element();
    preview.decorateConnection(path, edge);
    assert.match(path.children[0].textContent, /数据越界/);
    preview.clear();
    assert.equal(elements.lifecyclePanel.hidden, true);
    assert.equal(elements.compileLifecyclesButton['aria-pressed'], 'false');
    const clean = dom.element();
    preview.decorateNode(clean, graph.nodes[1]);
    assert.equal(clean.dataset.lifecycleId, undefined);
    graph.connections.pop();
    graph.connections.pop();
    preview.compile();
    assert.match(elements.lifecycleSummary.textContent, /编译失败/);
    preview.decorateNode(clean, graph.nodes[1]);
    assert.equal(clean.dataset.lifecycleId, undefined);
  } finally {
    if (oldDocument === undefined) delete globalThis.document;
    else globalThis.document = oldDocument;
  }
});

test('Context remains an explicit escape hatch without a leaking data edge', () => {
  const graph = loop();
  Object.assign(graph.nodes.find((item) => item.id === 'body'), {
    type: 'context_write', value_type: 'content', context_id_source: 'fixed', context_id: 'accumulator',
  });
  graph.nodes.push(node('read', 'context_read', { value_type: 'content', context_id_source: 'fixed', context_id: 'accumulator' }));
  graph.connections.find((edge) => edge.fromId === 'f' && edge.fromPortId === 'control-out').toId = 'read';
  graph.connections.push(control('read', 'o'), data('f', 'body', 'item-out', 'value-in'), data('read', 'o', 'value-out'));
  assert.deepEqual(compileLifecycles(graph).errors, []);
});

test('two sequential loops get sibling bodies and cannot exchange local values', () => {
  const graph = loop();
  graph.nodes.push(node('g', 'foreach', { item_type: 'content' }), node('body2'));
  graph.connections.find((edge) => edge.fromId === 'f' && edge.fromPortId === 'control-out').toId = 'g';
  graph.connections.push(control('g', 'body2', 'loop-out'), control('body2', 'g', 'control-out', 'loop-in'), control('g', 'o'));
  const result = compileLifecycles(graph);
  assert.deepEqual(result.errors, []);
  assert.deepEqual(result.scopes.slice(1).map((scope) => scope.parentId), ['L0', 'L0']);
  graph.connections.push(data('body', 'body2'));
  assert.match(messages(compileLifecycles(graph)), /数据越界/);
});

test('nested foreach is not silently permitted by the existing no-branch loop rule', () => {
  const graph = loop();
  Object.assign(graph.nodes.find((item) => item.id === 'body'), { type: 'foreach', item_type: 'content' });
  graph.nodes.push(node('nested'));
  graph.connections.push(control('body', 'nested', 'loop-out'), control('nested', 'body', 'control-out', 'loop-in'));
  assert.match(messages(compileLifecycles(graph)), /循环体内不允许多分支节点/);
});


test('lifecycle HTML labels remain intact UTF-8', async () => {
  const { readFile } = await import('node:fs/promises');
  const html = await readFile(new URL('./static/workflow_edit.html', import.meta.url), 'utf8');
  assert.match(html, /id="compileLifecyclesButton"[^>]*>\u7f16\u8bd1\u751f\u547d\u5468\u671f<\/button>/);
  assert.match(html, /id="clearLifecyclesButton"[^>]*>\u6e05\u9664\u7740\u8272<\/button>/);
  assert.ok(html.includes('aria-label="\u751f\u547d\u5468\u671f\u7f16\u8bd1\u9884\u89c8"'));
  assert.ok(html.includes('aria-label="\u751f\u547d\u5468\u671f\u56fe\u4f8b"'));
  assert.ok(html.includes('\u9759\u6001\u7f16\u8bd1\u63a7\u5236\u6811'));
  assert.ok(html.includes('\u4ec5\u9759\u6001\u9884\u89c8\uff0c\u4e0d\u6267\u884c Workflow'));
  assert.ok(html.includes('\u540c\u4e00\u7a7a\u95f4\u5185\u90e8'));
  const preview = html.match(/<section id="lifecyclePanel"[\s\S]*?<\/section>/)?.[0];
  assert.ok(preview);
  assert.doesNotMatch(preview, /\?{2,}|\uFFFD/);
});

// Exercise the same protocol documents against all three lifecycle validators.
test('editor preview and both backend validators agree on lifecycle fixtures', () => {
  const script = `import json, sys
sys.path.insert(0, sys.argv[1])
from test_workflow_lifecycles import test_cases
from workflow_validator import WorkflowValidationError, validate_workflow
results = []
for case in test_cases():
    try:
        validate_workflow(case['workflow'])
        accepted = True
    except WorkflowValidationError:
        accepted = False
    results.append({**case, 'accepted': accepted})
print(json.dumps(results))
`;
  const results = [];
  for (const backend of ['agent_runtime', 'manager_webui']) {
    const child = spawnSync(process.env.PYTHON || 'python', ['-c', script, backend], {
      cwd: fileURLToPath(new URL('..', import.meta.url)), encoding: 'utf8', timeout: 30000,
    });
    assert.ifError(child.error);
    assert.equal(child.status, 0, `${backend}: ${child.stderr}`);
    const cases = JSON.parse(child.stdout);
    for (const entry of cases) {
      const preview = compileLifecycles(entry.workflow);
      assert.equal(entry.accepted, !entry.error, `${backend}: ${entry.name}`);
      assert.equal(preview.errors.length === 0, entry.accepted, `${backend} vs editor: ${entry.name}`);
    }
    results.push(cases);
  }
  assert.deepEqual(results[0], results[1]);
});
