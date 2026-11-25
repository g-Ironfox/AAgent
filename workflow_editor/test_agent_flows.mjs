import assert from 'node:assert/strict';
import fs from 'node:fs';
import { test } from 'node:test';
import { loadSnapshot, parseWorkflowText, state, workflowSnapshot } from './static/workflow/domain/serialization.js';

for (const file of ['initial-agent.design.json', 'executor-agent.design.json', 'sidecar.design.json']) {
  const design = JSON.parse(fs.readFileSync(new URL('../workflow-design/' + file, import.meta.url), 'utf8'));
  for (const { filename, workflow } of design.workflows) {
    test(filename + ' preserves all connections across editor import/save/reload', () => {
      const imported = parseWorkflowText(JSON.stringify(workflow));
      assert.equal(imported.schema_version, '2.0');
      loadSnapshot(imported);
      const saved = workflowSnapshot();
      assert.equal(saved.name, filename);
      assert.equal(saved.nodes.length, workflow.nodes.length);
      const connections = workflow.connections.map(({ id, ...edge }) => edge);
      assert.deepEqual(saved.connections, connections);
      assert.equal(new Set(state.connections.map(edge => edge.id)).size, workflow.connections.length);
      loadSnapshot(saved);
      assert.deepEqual(workflowSnapshot().connections, connections);
    });
  }
}
