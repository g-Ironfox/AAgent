import assert from 'node:assert/strict';
import { test } from 'node:test';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { addNode, loadSnapshot, state, workflowSnapshot } from './static/workflow/domain/serialization.js';
import { portsForNode } from './static/workflow/domain/node-contract.js';
import { compileLifecycles } from './static/workflow/domain/lifecycle.js';
import { isValidConnection } from './static/workflow/domain/connection-rules.js';
import { bindNodeFunctions, validateFunctions } from './static/workflow/domain/functions.js';
import { prepareStructDefinitions, remapStructReferences } from './static/workflow/domain/struct-editing.js';

function fixture() {
  const child = spawnSync(process.env.PYTHON || 'python', ['-c', 'import json,sys; sys.path.insert(0,"agent"); from test_workflow_functions import function_document; print(json.dumps(function_document(nested=True)))'], {
    cwd: fileURLToPath(new URL('..', import.meta.url)), encoding: 'utf8', timeout: 30000,
  });
  assert.equal(child.status, 0, child.stderr);
  return JSON.parse(child.stdout);
}

test('nested functions round-trip without storing ordinary node membership', () => {
  const source = fixture();
  assert.equal(loadSnapshot(source), true);
  const call = state.nodes.find((n) => n.id === 'callB');
  assert.equal(call.function_id, undefined);
  assert.equal(call.callee_id, 'B');
  assert.deepEqual(portsForNode(call).map((p) => [p.direction, p.id]), [
    ['input', 'control-in'], ['input', 'function:text'], ['output', 'control-out'], ['output', 'function:text'],
  ]);
  const snapshot = workflowSnapshot();
  assert.equal(snapshot.nodes.find((n) => n.id === 'callB').function_id, undefined);
  assert.deepEqual(snapshot.nodes.find((n) => n.id === 'callB').arguments, { function_id: 'B' });
  assert.equal(JSON.stringify(snapshot).includes('_function_'), false);
  assert.equal(JSON.stringify(snapshot).includes('callee_id'), false);
  assert.equal(loadSnapshot(snapshot), true);
  assert.deepEqual(workflowSnapshot(), snapshot);
  const child = spawnSync(process.env.PYTHON || 'python', ['-c', 'import json,sys; sys.path.insert(0,"agent"); from workflow_validator import validate_workflow; validate_workflow(json.load(sys.stdin))'], {
    cwd: fileURLToPath(new URL('..', import.meta.url)), input: JSON.stringify(snapshot), encoding: 'utf8', timeout: 30000,
  });
  assert.equal(child.status, 0, child.stderr);
});

test('each function gets an independent lifecycle root and no direct outside connections', () => {
  assert.equal(loadSnapshot(fixture()), true);
  const result = compileLifecycles(workflowSnapshot());
  assert.deepEqual(result.errors, []);
  assert.equal(result.scopes.filter((s) => s.parentId === null).length, 3);
  assert.notEqual(result.nodeScopes.get('Ain'), result.nodeScopes.get('Bin'));
  assert.equal(result.nodeFunctions.get('callA'), null);
  assert.equal(result.nodeFunctions.get('callB'), 'A');
  assert.equal(state.nodes.find((n) => n.id === 'callB').function_id, undefined);
  const edge = { id: 'illegal', fromId: 'Ain', fromPortId: 'function:text', toId: 'callA', toPortId: 'function:text', type: 'content' };
  // Port compatibility is independent of static lifecycle validation.
  assert.equal(isValidConnection(edge, state.nodes), true);
  const invalid = compileLifecycles({ ...workflowSnapshot(), connections: [...state.connections, edge] });
  assert.ok(invalid.errors.length);
});

test('function node creation only declares the callee', () => {
  assert.equal(loadSnapshot(fixture()), true);
  const node = addNode('function_call', { ...state.metadata.functions[1], function_id: 'A' });
  assert.equal(node.callee_id, 'B');
  assert.equal(node.function_id, undefined);
  assert.equal(portsForNode(node).length, 4);
});

test('legacy body labels are removed and DFS reports cross-function control flow', () => {
  const source = fixture();
  source.nodes.find((n) => n.id === 'callB').function_id = 'obsolete_owner';
  assert.equal(loadSnapshot(source), true);
  assert.deepEqual(compileLifecycles(workflowSnapshot()).errors, []);
  assert.equal(workflowSnapshot().nodes.find((n) => n.id === 'callB').function_id, undefined);
  const snapshot = workflowSnapshot();
  snapshot.connections.find((e) => e.fromId === 'Ain' && e.type === 'control').toId = 'Bout';
  assert.ok(compileLifecycles(snapshot).errors.some((e) => e.message.includes('跨越函数边界')));
});

test('input/output interfaces can use the same name with different types and Structs', () => {
  const structs = [{ id: 'Record', name: 'Record', color: '#3976A8', fields: [] }];
  const functions = validateFunctions([{ id: 'f', name: 'Convert', input_ports: [{ name: 'value', type: 'content' }], output_ports: [{ name: 'value', type: 'struct:Record' }] }], structs);
  const nodes = [{ id: 'call', type: 'function_call', callee_id: 'f' }];
  bindNodeFunctions(nodes, functions);
  const ports = portsForNode(nodes[0]);
  assert.equal(ports.find((p) => p.id === 'function:value' && p.direction === 'input').type, 'content');
  assert.equal(ports.find((p) => p.id === 'function:value' && p.direction === 'output').type, 'struct:Record');
  const { idMap } = prepareStructDefinitions([{ ...structs[0], name: 'Renamed' }]);
  const doc = { metadata: { functions } };
  remapStructReferences(doc, idMap);
  assert.equal(doc.metadata.functions[0].output_ports[0].type, 'struct:Renamed');
});

test('recursive calls are reported by lifecycle compilation', () => {
  const source = fixture();
  source.nodes.push({ id: 'back', type: 'function_call', function_id: 'B', arguments: { function_id: 'A' } });
  source.connections.find((e) => e.fromId === 'Bin' && e.type === 'control').toId = 'back';
  source.connections.push({ id: 'back-return', fromId: 'back', fromPortId: 'control-out', toId: 'Bout', toPortId: 'control-in', type: 'control' });
  const result = compileLifecycles(source);
  assert.ok(result.errors.some((e) => e.message.includes('递归函数调用')));
});

test('invalid declarations and stale snapshots do not replace the current document', () => {
  const source = fixture();
  assert.equal(loadSnapshot(source), true);
  const before = workflowSnapshot();
  const invalid = structuredClone(source);
  invalid.metadata.functions.push(structuredClone(invalid.metadata.functions[0]));
  assert.equal(loadSnapshot(invalid), false);
  assert.deepEqual(workflowSnapshot(), before);
  source.nodes.find((n) => n.id === 'callA').input_ports = [{ name: 'stale', type: 'content' }];
  assert.equal(loadSnapshot(source), false);
  assert.deepEqual(workflowSnapshot(), before);
});
