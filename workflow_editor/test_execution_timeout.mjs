import assert from 'node:assert/strict';
import { test } from 'node:test';
import { loadSnapshot, state, workflowSnapshot } from './static/workflow/domain/serialization.js';

test('workflow execution timeout survives editor import and export', () => {
  const workflow = workflowSnapshot();
  workflow.metadata.max_execution_time_seconds = 42;
  assert.equal(loadSnapshot(workflow), true);
  assert.equal(state.metadata.max_execution_time_seconds, 42);
  assert.equal(workflowSnapshot().metadata.max_execution_time_seconds, 42);
});
