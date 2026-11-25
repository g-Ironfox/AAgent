import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { isValidConnection } from './static/workflow/domain/connection-rules.js';
import { loadSnapshot, state, workflowSnapshot } from './static/workflow/domain/serialization.js';
import { compileLifecycles } from './static/workflow/domain/lifecycle.js';

for (const role of ['main', 'stable-main', 'iterator', 'bootstrap']) {
  test('ALFWorld bundle ' + role + ' keeps valid edges and local function lifecycles', () => {
    const file = new URL('../docs/examples/alfworld-agent/alfworld-agent-' + role + '.flow', import.meta.url);
    const workflow = JSON.parse(readFileSync(file, 'utf8'));
    assert.equal(loadSnapshot(workflow), true);
    assert.equal(state.connections.length, workflow.connections.length);
    for (const edge of workflow.connections) {
      assert.ok(state.connections.some((saved) =>
        ['fromId', 'fromPortId', 'toId', 'toPortId', 'type'].every((key) => saved[key] === edge[key])));
    }
    assert.ok(state.connections.every((edge) => isValidConnection(edge, state.nodes)));
    const saved = workflowSnapshot();
    assert.equal(loadSnapshot(saved), true);
    assert.deepEqual(workflowSnapshot(), saved);
    assert.deepEqual(compileLifecycles(saved).errors, []);
  });
}
