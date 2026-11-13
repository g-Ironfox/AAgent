import assert from 'node:assert/strict';
import { test } from 'node:test';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { readFileSync } from 'node:fs';
import { loadSnapshot, state, workflowSnapshot, resetWorkflow, addNode } from './static/workflow/domain/serialization.js';
import { portsForNode } from './static/workflow/domain/node-contract.js';
import { applyToolDeclaration, toolFromSchema } from './static/workflow/domain/tool-contract.js';

const port = (name, type = 'content') => ({ name, type });
function fixture(kind, mode = 'sync') {
  const outputs = [port(kind === 'local' ? 'output' : 'result')];
  const output = mode === 'async' ? 'task_id' : outputs[0].name;
  return {
    schema_version: '2.0', name: kind + '_' + mode,
    metadata: { structs: [], tools: [{ name: 'echo', kind, input_ports: [port('value')], output_ports: outputs }] },
    input_ports: [port('text')], output_ports: [port('result')], workflow_nodes: [],
    nodes: [
      { id: 'input', type: 'input', workflowPorts: [{ id: 'workflow:text', ...port('text') }] },
      { id: 'tool', type: 'tool', arguments: {
        tool: 'echo', parameters: [port('value')], outputs, mode,
        timeout_ms: mode === 'async' ? 600000 : 10000,
        callback: mode === 'async' ? { type: 'redis', queue: 'results', event_type: 'done', on: ['completed', 'failed'] } : null,
      } },
      { id: 'output', type: 'output', workflowPorts: [{ id: 'workflow:result', ...port('result') }] },
    ],
    connections: [
      { id: 'c1', fromId: 'input', fromPortId: 'control-out', toId: 'tool', toPortId: 'control-in', type: 'control' },
      { id: 'c2', fromId: 'tool', fromPortId: 'control-out', toId: 'output', toPortId: 'control-in', type: 'control' },
      { id: 'd1', fromId: 'input', fromPortId: 'workflow:text', toId: 'tool', toPortId: 'value', type: 'content' },
      { id: 'd2', fromId: 'tool', fromPortId: output, toId: 'output', toPortId: 'workflow:result', type: 'content' },
    ],
  };
}

function verifyBackends(workflows) {
  const script = "import json, sys, types\nfrom unittest.mock import Mock, patch\nsys.path.insert(0, sys.argv[1])\nfrom workflow_validator import validate_workflow\nfor workflow in json.load(sys.stdin):\n    validate_workflow(workflow)\n    if sys.argv[1] != 'agent': continue\n    from workflow_parser import parse_workflow\n    from workflow_nodes import run_workflow_map, propagate_workflow_output\n    graph = parse_workflow(workflow)\n    declaration = workflow['metadata']['tools'][0]\n    assert graph[1]['_tool_kind'] == declaration['kind']\n    propagate_workflow_output(graph, graph[0], 'workflow:text', 'hello')\n    fake = types.ModuleType('tools.tool')\n    fake.execute_tool = Mock(return_value={'message': 'hello'})\n    async_mode = workflow['nodes'][1]['arguments']['mode'] == 'async'\n    with patch.dict(sys.modules, {'tools.tool': fake}), patch('tool_server_client.call_remote_tool', return_value='task-1' if async_mode else 'hello') as remote:\n        result = run_workflow_map(graph, 0)\n    if declaration['kind'] == 'local':\n        fake.execute_tool.assert_called_once_with('tool', 'echo', {'value': 'hello'})\n        remote.assert_not_called()\n        assert result == {'result': '{\"message\": \"hello\"}'}\n    else:\n        args = workflow['nodes'][1]['arguments']\n        remote.assert_called_once_with('echo', {'value': 'hello'}, 'async' if async_mode else 'wait', args['timeout_ms'], args['callback'] if async_mode else None)\n        assert result == {'result': 'task-1' if async_mode else 'hello'}\n";
  for (const backend of ['agent', 'manager_webui']) {
    const result = spawnSync(process.env.PYTHON || 'python', ['-c', script, backend], {
      cwd: fileURLToPath(new URL('..', import.meta.url)), input: JSON.stringify(workflows), encoding: 'utf8', timeout: 30000,
    });
    assert.ifError(result.error);
    assert.equal(result.status, 0, backend + ': ' + result.stderr);
  }
}

test('one Tool node round-trips local, remote sync and remote async through both backends', () => {
  const workflows = [];
  for (const [kind, mode] of [['local', 'sync'], ['remote', 'sync'], ['remote', 'async']]) {
    const workflow = fixture(kind, mode);
    assert.equal(loadSnapshot(workflow), true);
    const snapshot = workflowSnapshot();
    assert.equal(snapshot.remote_tools, undefined);
    assert.deepEqual(snapshot.metadata.tools, workflow.metadata.tools);
    assert.deepEqual(snapshot.connections, workflow.connections);
    assert.equal(snapshot.nodes[1].type, 'tool');
    assert.equal(portsForNode(state.nodes[1]).find((item) => item.direction === 'output' && item.type !== 'control').id,
      mode === 'async' ? 'task_id' : kind === 'local' ? 'output' : 'result');
    assert.equal(loadSnapshot(snapshot), true);
    assert.deepEqual(workflowSnapshot(), snapshot);
    workflows.push(snapshot);
  }
  verifyBackends(workflows);
});

test('legacy tool nodes migrate without losing connections or async callbacks', () => {
  const workflows = [];
  for (const [kind, mode] of [['local', 'sync'], ['remote', 'sync'], ['remote', 'async']]) {
    const workflow = fixture(kind, mode);
    const declaration = workflow.metadata.tools[0];
    delete workflow.metadata.tools;
    const node = workflow.nodes[1];
    node.type = kind === 'local' ? 'local_tool' : mode === 'sync' ? 'remote_sync_tool' : 'remote_async_tool';
    delete node.arguments.mode;
    if (kind === 'local') {
      node.arguments = { tool: 'echo', parameters: ['value'] };
    } else {
      workflow.remote_tools = [{ name: declaration.name, input_ports: declaration.input_ports, output_ports: declaration.output_ports }];
      if (mode === 'async') delete node.arguments.outputs;
      else delete node.arguments.callback;
    }
    assert.equal(loadSnapshot(workflow), true);
    const migrated = workflowSnapshot();
    assert.equal(migrated.nodes[1].type, 'tool');
    assert.deepEqual(migrated.connections, workflow.connections);
    assert.deepEqual(migrated.metadata.tools, [declaration]);
    workflows.push(migrated);
  }
  verifyBackends(workflows);
});

test('tool schema conversion preserves remote types and the local output contract', () => {
  const schema = { name: 'echo', inputSchema: { properties: { value: { type: 'array' } } }, outputSchema: { 'x-workflow-port-type': 'map-content', type: 'object' } };
  assert.deepEqual(toolFromSchema(schema, 'remote').input_ports, [port('value', 'list-content')]);
  assert.deepEqual(toolFromSchema(schema, 'remote').output_ports, [port('result', 'map-content')]);
  assert.deepEqual(toolFromSchema(schema, 'local').input_ports, [port('value')]);
  assert.deepEqual(toolFromSchema(schema, 'local').output_ports, [port('output')]);
});

test('switching an async remote node to local resets mode, timeout and callback', () => {
  const node = { mode: 'async', timeout_ms: 600000, callback: { type: 'redis' } };
  const declaration = fixture('local').metadata.tools[0];
  applyToolDeclaration(node, declaration);
  assert.equal(node.mode, 'sync');
  assert.equal(node.timeout_ms, 10000);
  assert.equal(node.callback, null);
  assert.deepEqual(node.parameters, declaration.input_ports);
});

test('duplicate tool names and local async mode are rejected without altering the loaded workflow', () => {
  assert.equal(loadSnapshot(fixture('local')), true);
  const before = workflowSnapshot();
  const workflow = fixture('local');
  workflow.metadata.tools.push({ ...workflow.metadata.tools[0], name: 'ECHO', kind: 'remote' });
  assert.equal(loadSnapshot(workflow), false);
  assert.deepEqual(workflowSnapshot(), before);
  assert.equal(loadSnapshot(fixture('local', 'async')), false);
});

test('an unbound Tool can be created and saved as an editor draft', () => {
  assert.equal(resetWorkflow(), true);
  assert.equal(addNode('tool').type, 'tool');
  assert.equal(loadSnapshot(workflowSnapshot()), true);
});

test('tool library is unified and retains Workflow integration mounts and metadata controls', () => {
  const html = readFileSync(new URL('./static/workflow_edit.html', import.meta.url), 'utf8');
  assert.match(html, /id="workflowNodeLibrary"/);
  assert.match(html, /data-add-node="tool"/);
  assert.doesNotMatch(html, /data-add-node="(?:local_tool|remote_sync_tool|remote_async_tool)"/);
  assert.match(html, /id="toolInspectorTemplate"/);
  assert.match(html, /data-tool-kind value="local"/);
  assert.match(html, /data-tool-kind value="remote"/);
  assert.match(html, /data-remote-tool-suggestions class="remote-tool-suggestions"/);
  assert.doesNotMatch(html, /<select data-remote-tool-name/);
  const workflowJs = readFileSync(new URL('./static/workflow.js', import.meta.url), 'utf8');
  assert.match(workflowJs, /candidate\.kind === option\.dataset\.toolKind/);
  assert.match(workflowJs, /\.filter\(\(tool\) =>/);
  assert.match(workflowJs, /Number\(right\.kind === kind\) - Number\(left\.kind === kind\)/);
  assert.doesNotMatch(workflowJs, /\.slice\(0, 8\)/);
});

test('both backends reject mismatched declarations, invalid kinds, callbacks and local async mode', () => {
  const workflows = [];
  const invalid = (mutate) => { const workflow = fixture('remote', 'async'); mutate(workflow); workflows.push(workflow); };
  invalid((workflow) => { workflow.metadata.tools[0].kind = 'invalid'; });
  invalid((workflow) => { workflow.metadata.tools[0].input_ports = [port('renamed')]; });
  invalid((workflow) => { workflow.metadata.tools.push({ ...workflow.metadata.tools[0], name: 'ECHO' }); });
  invalid((workflow) => { workflow.metadata.tools[0].output_ports = [port('value', 'struct:external')]; });
  invalid((workflow) => { workflow.metadata.tools[0].input_ports = [port('control-in')]; });
  invalid((workflow) => { workflow.nodes[1].arguments.callback.on = []; });
  invalid((workflow) => { workflow.nodes[1].arguments.callback.on = ['invalid']; });
  invalid((workflow) => { workflow.nodes[1].arguments.mode = 'invalid'; });
  workflows.push(fixture('local', 'async'));
  for (const backend of ['agent', 'manager_webui']) {
    const result = spawnSync(process.env.PYTHON || 'python', ['-c', "import json, sys\nsys.path.insert(0, sys.argv[1])\nfrom workflow_validator import validate_workflow, WorkflowValidationError\nfor workflow in json.load(sys.stdin):\n    try:\n        validate_workflow(workflow)\n    except WorkflowValidationError:\n        continue\n    raise AssertionError('accepted malformed Tool workflow')\n", backend], {
      cwd: fileURLToPath(new URL('..', import.meta.url)), input: JSON.stringify(workflows), encoding: 'utf8', timeout: 30000,
    });
    assert.ifError(result.error);
    assert.equal(result.status, 0, backend + ': ' + result.stderr);
  }
});

test('legacy local nodes merge parameter declarations without dropping existing data ports', () => {
  const workflow = fixture('local');
  delete workflow.metadata.tools;
  workflow.nodes[1].type = 'local_tool';
  workflow.nodes[1].arguments = { tool: 'echo', parameters: ['value'] };
  workflow.nodes.push({ id: 'second-local', type: 'local_tool', arguments: { tool: 'echo', parameters: ['other'] } });
  assert.equal(loadSnapshot(workflow), true);
  assert.deepEqual(workflowSnapshot().metadata.tools[0].input_ports, [port('value'), port('other')]);
  assert.deepEqual(state.nodes[1].parameters, [port('value'), port('other')]);
  assert.equal(state.connections.length, workflow.connections.length);
});
