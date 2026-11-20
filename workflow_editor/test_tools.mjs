import assert from 'node:assert/strict';
import { test } from 'node:test';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { readFileSync } from 'node:fs';
import { loadSnapshot, state, workflowSnapshot, resetWorkflow, addNode } from './static/workflow/domain/serialization.js';
import { createNode, portsForNode } from './static/workflow/domain/node-contract.js';
import { toolPreview } from './static/workflow/inspector/tool-definition.js';
import { applyToolDeclaration, toolFromSchema } from './static/workflow/domain/tool-contract.js';
import { createIntegrationInspector } from './static/workflow/inspector/integrations.js';

const port = (name, type = 'content') => ({ name, type });

test('construct_tool emits one content Tool JSON and exposes fixed/port controls', () => {
  const node = createNode('construct_tool', []);
  assert.equal(node.schema_source, 'fixed');
  assert.equal(node.required_source, 'fixed');
  assert.equal(toolPreview(node), JSON.stringify({ type: 'function', function: {
    name: 'my_tool', description: '', parameters: { type: 'object', properties: {} },
  } }, null, 2));
  assert.deepEqual(portsForNode(node).map(({ id, type }) => [id, type]), [
    ['control-in', 'control'], ['control-out', 'control'], ['tool-out', 'content'],
  ]);
  node.required_source = 'port';
  assert.equal(portsForNode(node).find((item) => item.id === 'required-in').type, 'list-content');
  node.schema_source = 'port';
  assert.equal(portsForNode(node).find((item) => item.id === 'schema-in').type, 'content');
});

test('construct_tool preview reports invalid schemas and preserves inherited required fields', () => {
  const node = createNode('construct_tool', []);
  node.schema = { type: 'object', properties: { text: { type: 'string' } }, required: ['text'] };
  assert.deepEqual(JSON.parse(toolPreview(node)).function.parameters.required, ['text']);
  node.required = [];
  assert.deepEqual(JSON.parse(toolPreview(node)).function.parameters.required, []);
  node.schema = '{';
  assert.throws(() => toolPreview(node), SyntaxError);
});

test('LLM tool-call mode exposes a list-content available-tools input', () => {
  const disabled = portsForNode({ id: 'llm-off', type: 'llm', tool_calls: false });
  assert.equal(disabled.some((item) => item.id === 'available-tools-in'), false);
  const enabled = portsForNode({ id: 'llm-on', type: 'llm', tool_calls: true });
  const availableToolsPort = enabled.find((item) => item.id === 'available-tools-in');
  assert.equal(availableToolsPort.direction, 'input');
  assert.equal(availableToolsPort.type, 'list-content');
  assert.equal(availableToolsPort.multiple, false);
  assert.match(availableToolsPort.title, /metadata\.tools/);
  const definitions = portsForNode({ id: 'llm-json', type: 'llm', tool_calls: true, tools_source: 'definitions' });
  assert.equal(definitions.some((item) => item.id === 'available-tools-in'), false);
  assert.equal(definitions.find((item) => item.id === 'tools-in').type, 'list-content');
});
function fixture(kind, mode = 'sync') {
  const outputs = [port(kind === 'local' ? 'output' : 'result')];
  const output = mode === 'async' ? 'task_id' : outputs[0].name;
  return {
    schema_version: '2.0', name: kind + '_' + mode,
    metadata: { structs: [], tools: [{ name: 'echo', kind, input_ports: [port('value')], output_ports: outputs }] },
    input_ports: [port('text')], output_ports: [port('result')], subprocess_workflow_files: [],
    nodes: [
      { id: 'input', type: 'input', workflowPorts: [{ id: 'workflow:text', ...port('text') }] },
      { id: 'tool', type: mode === 'async' ? 'remote_async_tool' : 'tool', arguments: {
        tool: 'echo', parameters: [port('value')], ...(mode === 'async' ? {} : { outputs, mode }),
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
  const script = "import json, sys, types\nfrom unittest.mock import Mock, patch\nsys.path.insert(0, sys.argv[1])\nfrom workflow_validator import validate_workflow\nfor workflow in json.load(sys.stdin):\n    validate_workflow(workflow)\n    if sys.argv[1] != 'agent': continue\n    from workflow_parser import parse_workflow\n    from workflow_nodes import propagate_workflow_output\n    from test_support import run_scheduled_workflow\n    graph = parse_workflow(workflow)\n    declaration = workflow['metadata']['tools'][0]\n    assert graph[1]['_tool_kind'] == declaration['kind']\n    propagate_workflow_output(graph, graph[0], 'workflow:text', 'hello')\n    fake = types.ModuleType('tools.tool')\n    fake.execute_tool = Mock(return_value=({'message': 'hello'} if declaration['output_ports'] == [{'name': 'output', 'type': 'content'}] else {port['name']: ({'key': 'value'} if port['type'] == 'map-content' else 'hello') for port in declaration['output_ports']}))\n    async_mode = workflow['nodes'][1]['type'] == 'remote_async_tool'\n    with patch.dict(sys.modules, {'tools.tool': fake}), patch('tool_server_client.call_remote_tool', return_value='task-1' if async_mode else 'hello') as remote:\n        result = run_scheduled_workflow(graph, 0)\n    if declaration['kind'] == 'local':\n        fake.execute_tool.assert_called_once_with('tool', 'echo', {'value': 'hello'}, preserve_result=True)\n        remote.assert_not_called()\n        assert result == {'result': 'hello' if declaration['output_ports'] != [{'name': 'output', 'type': 'content'}] else '{\"message\": \"hello\"}'}\n    else:\n        args = workflow['nodes'][1]['arguments']\n        remote.assert_called_once_with('echo', {'value': 'hello'}, 'async' if async_mode else 'wait', args['timeout_ms'], args['callback'] if async_mode else None)\n        assert result == {'result': 'task-1' if async_mode else 'hello'}\n";
  for (const backend of ['agent', 'manager_webui']) {
    const result = spawnSync(process.env.PYTHON || 'python', ['-c', script, backend], {
      cwd: fileURLToPath(new URL('..', import.meta.url)), input: JSON.stringify(workflows), encoding: 'utf8', timeout: 30000,
    });
    assert.ifError(result.error);
    assert.equal(result.status, 0, backend + ': ' + result.stderr);
  }
}

test('sync Tool and remote async Tool round-trip through both backends', () => {
  const workflows = [];
  for (const [kind, mode] of [['local', 'sync'], ['remote', 'sync'], ['remote', 'async']]) {
    const workflow = fixture(kind, mode);
    assert.equal(loadSnapshot(workflow), true);
    const snapshot = workflowSnapshot();
    assert.equal(snapshot.remote_tools, undefined);
    assert.deepEqual(snapshot.metadata.tools, workflow.metadata.tools);
    assert.deepEqual(snapshot.connections, workflow.connections.map(({ id, ...connection }) => connection));
    assert.equal(snapshot.nodes[1].type, mode === 'async' ? 'remote_async_tool' : 'tool');
    assert.equal(portsForNode(state.nodes[1]).find((item) => item.direction === 'output' && item.type !== 'control').id,
      mode === 'async' ? 'task_id' : kind === 'local' ? 'output' : 'result');
    assert.equal(loadSnapshot(snapshot), true);
    assert.deepEqual(workflowSnapshot(), snapshot);
    workflows.push(snapshot);
  }
  verifyBackends(workflows);
});

test('local Tool keeps each declared result as an independent output port', () => {
  const workflow = fixture('local');
  const outputs = [port('answer'), port('details', 'map-content')];
  workflow.metadata.tools[0].output_ports = outputs;
  workflow.nodes[1].arguments.outputs = outputs;
  workflow.connections.find((connection) => connection.id === 'd2').fromPortId = 'answer';
  assert.equal(loadSnapshot(workflow), true);
  assert.deepEqual(portsForNode(state.nodes[1]).filter((item) => item.direction === 'output' && item.type !== 'control').map(({ id, type }) => ({ name: id, type })), outputs);
  const snapshot = workflowSnapshot();
  assert.equal(loadSnapshot(snapshot), true);
  assert.deepEqual(workflowSnapshot(), snapshot);
  verifyBackends([snapshot]);
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
    assert.equal(migrated.nodes[1].type, mode === 'async' ? 'remote_async_tool' : 'tool');
    assert.deepEqual(migrated.connections, workflow.connections.map(({ id, ...connection }) => connection));
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
  assert.deepEqual(toolFromSchema({ ...schema, outputSchema: null }, 'local').output_ports, [port('output')]);
  const localSchema = { ...schema, outputSchema: { type: 'object', properties: {
    answer: { type: 'string' }, details: { type: 'object', 'x-workflow-port-type': 'map-content' },
  } } };
  assert.deepEqual(toolFromSchema(localSchema, 'local').output_ports, [port('answer'), port('details', 'map-content')]);
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

test('former unified async nodes migrate to remote async without losing callbacks or connections', () => {
  const workflow = fixture('remote', 'async');
  const node = workflow.nodes[1];
  node.type = 'tool';
  node.arguments.mode = 'async';
  node.arguments.outputs = workflow.metadata.tools[0].output_ports;
  assert.equal(loadSnapshot(workflow), true);
  const saved = workflowSnapshot();
  assert.equal(saved.nodes[1].type, 'remote_async_tool');
  assert.equal(saved.nodes[1].arguments.mode, undefined);
  assert.deepEqual(saved.nodes[1].arguments.callback, node.arguments.callback);
  assert.deepEqual(saved.connections, workflow.connections.map(({ id, ...connection }) => connection));
  verifyBackends([saved]);
});

test('async Tool rejects local declarations and preserves its timeout and callback when updated', () => {
  assert.equal(loadSnapshot(fixture('local', 'async')), false);
  const node = { type: 'remote_async_tool', timeout_ms: 60000, callback: { type: 'redis' } };
  assert.throws(() => applyToolDeclaration(node, fixture('local').metadata.tools[0]));
  applyToolDeclaration(node, fixture('remote').metadata.tools[0]);
  assert.equal(node.timeout_ms, 60000);
  assert.deepEqual(node.callback, { type: 'redis' });
  assert.equal(node.mode, undefined);
  assert.equal(node.outputs, undefined);
  assert.deepEqual(node.parameters, [port('value')]);
});

test('async Tool inspector only lists metadata Remote Tools', (t) => {
  const originalDocument = globalThis.document;
  globalThis.document = { createElement: () => ({}) };
  t.after(() => {
    if (originalDocument === undefined) delete globalThis.document;
    else globalThis.document = originalDocument;
  });
  const select = { replaceChildren(...options) { this.options = options; } };
  const fields = new Map([['[data-field="tool"]', select]]);
  const mount = { querySelector(selector) {
    if (!fields.has(selector)) fields.set(selector, { querySelector: (key) => mount.querySelector(key), querySelectorAll: () => [] });
    return fields.get(selector);
  } };
  const inspector = createIntegrationInspector({ elements: { inspectorContent: mount }, editor: { editorState: {} } });
  inspector.setRemoteToolReferences([{ name: 'local-echo', kind: 'local' }, { name: 'remote-echo', kind: 'remote' }]);
  inspector.prepare({ type: 'remote_async_tool', tool: 'remote-echo', callback: null });
  assert.deepEqual(select.options.map((option) => option.value), ['remote-echo']);
  assert.equal(select.value, 'remote-echo');
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
  const jsonTool = addNode('json_tool');
  assert.equal(jsonTool.type, 'json_tool');
  assert.deepEqual(portsForNode(jsonTool).filter((item) => item.type !== 'control').map(({ id, direction, type }) => ({ id, direction, type })), [
    { id: 'tool-name', direction: 'input', type: 'content' },
    { id: 'arguments-json', direction: 'input', type: 'content' },
    { id: 'result-json', direction: 'output', type: 'content' },
    { id: 'error-json', direction: 'output', type: 'content' },
  ]);
  assert.equal(addNode('remote_async_tool').type, 'remote_async_tool');
  assert.equal(loadSnapshot(workflowSnapshot()), true);
});

test('tool library is unified and retains Workflow integration mounts and metadata controls', () => {
  const html = readFileSync(new URL('./static/workflow_edit.html', import.meta.url), 'utf8');
  assert.match(html, /data-add-node="spawn_and_wait_subprocess"/);
  assert.doesNotMatch(html, /id="subprocessNodeLibrary"|subprocessWorkflowFileList/);
  assert.match(html, /data-add-node="tool"/);
  assert.match(html, /data-add-node="json_tool"/);
  assert.match(html, /id="json_toolInspectorTemplate"/);
  assert.doesNotMatch(html, /data-add-node="(?:local_tool|remote_sync_tool)"/);
  assert.match(html, /id="toolInspectorTemplate"/);
  assert.match(html, /data-add-node="remote_async_tool"/);
  assert.doesNotMatch(html, /data-tool-mode/);
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
  const asyncSyncNode = fixture('remote');
  asyncSyncNode.nodes[1].arguments.mode = 'async';
  workflows.push(asyncSyncNode);
  const syncCallback = fixture('remote');
  syncCallback.nodes[1].arguments.callback = fixture('remote', 'async').nodes[1].arguments.callback;
  workflows.push(syncCallback);
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

test('Tool control ports use Chinese labels', () => {
  const ports = portsForNode({ type: 'tool', parameters: [], outputs: [] });
  assert.equal(ports.find((item) => item.id === 'control-in').label, '触发');
  assert.equal(ports.find((item) => item.id === 'control-out').label, '下一步');
});
