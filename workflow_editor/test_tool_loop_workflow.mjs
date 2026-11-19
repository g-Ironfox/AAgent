import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { portsForNode } from './static/workflow/domain/node-contract.js';
import { isValidConnection } from './static/workflow/domain/connection-rules.js';
import { loadSnapshot, state, workflowSnapshot } from './static/workflow/domain/serialization.js';

const example = new URL('../docs/examples/tool-loop-agent.flow', import.meta.url);

test('tool-loop workflow preserves connections through editor import and export', () => {
  const workflow = JSON.parse(readFileSync(example, 'utf8'));
  assert.equal(loadSnapshot(workflow), true);
  assert.equal(state.connections.length, workflow.connections.length);
  for (const edge of workflow.connections) {
    assert.ok(state.connections.some((saved) =>
      ['fromId', 'fromPortId', 'toId', 'toPortId', 'type'].every((key) => saved[key] === edge[key])),
    `Editor dropped ${edge.fromId}:${edge.fromPortId} -> ${edge.toId}:${edge.toPortId}`);
  }
  assert.ok(state.connections.every((edge) => isValidConnection(edge, state.nodes)));
  const saved = workflowSnapshot();
  assert.equal(loadSnapshot(saved), true);
  assert.deepEqual(workflowSnapshot(), saved);
});

test('message ports accept native LLM calls and matching tool result IDs', () => {
  const message = { id: 'message', type: 'construct_message', role: 'assistant' };
  const llm = { id: 'llm', type: 'llm', tool_calls: true, think: true };
  const ports = portsForNode(message);
  for (const [id, type] of [['reasoning-in', 'content'], ['tool-calls-in', 'list-content'], ['tool-call-id-in', 'content']]) {
    assert.ok(ports.some(port => port.id === id && port.type === type));
  }
  const edge = { id: 'calls', fromId: 'llm', fromPortId: 'tool_calls', toId: 'message', toPortId: 'tool-calls-in', type: 'list-content' };
  assert.equal(isValidConnection(edge, [llm, message]), true);
  assert.equal(isValidConnection({ ...edge, type: 'content' }, [llm, message]), false);
});
