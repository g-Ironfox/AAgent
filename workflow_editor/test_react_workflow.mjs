import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { isValidConnection } from './static/workflow/domain/connection-rules.js';
import { loadSnapshot, state, workflowSnapshot } from './static/workflow/domain/serialization.js';

const example = new URL('../docs/examples/react-human-in-loop.flow', import.meta.url);

// Backend execution alone does not catch connections filtered by editor import.
test('ReAct example preserves every connection through editor import and export', () => {
  const workflow = JSON.parse(readFileSync(example, 'utf8'));
  assert.equal(loadSnapshot(workflow), true);
  assert.equal(state.connections.length, workflow.connections.length);
  for (const edge of workflow.connections) {
    assert.ok(state.connections.some((saved) =>
      ['fromId', 'fromPortId', 'toId', 'toPortId', 'type'].every((key) => saved[key] === edge[key])),
    `Editor dropped ${edge.fromId}:${edge.fromPortId} -> ${edge.toId}:${edge.toPortId}`);
  }
  assert.ok(state.connections.every((edge) => isValidConnection(edge, state.nodes)));
  for (const id of ['turn_count', 'build_count']) {
    assert.ok(state.connections.some((edge) => edge.fromId === id
      && edge.fromPortId === 'length-out' && edge.type === 'number'));
  }
  const saved = workflowSnapshot();
  assert.equal(loadSnapshot(saved), true);
  assert.deepEqual(workflowSnapshot(), saved);
});
