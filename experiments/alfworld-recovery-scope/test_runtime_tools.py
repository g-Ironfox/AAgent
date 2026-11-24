"""Verify the implemented registry, HTTP wrapper and typed workflow dispatch.

Only HTTP and Redis are substituted. The decorator, handler lookup, workspace
wrapper, candidate validator, parser and workflow output propagation are real.
"""
import copy
import importlib.util
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'agent_runtime'), str(ROOT / 'scripts')]
from build_evolving_iterator import build_bundle
from build_workflow_reference import workspace_tool_catalog
from process import WorkflowProcess
from workflow_nodes import current_workflow_process, workflow_tool


class RuntimeToolTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tools_dir = ROOT / 'agent_runtime/tools'
        environment = {
            'DEEPSEEK_BASE_URL': 'http://provider.test', 'DEEPSEEK_API_KEY': 'test',
            'KIMI_BASE_URL': 'http://provider.test', 'KIMI_API_KEY': 'test',
            'TAVILY_API_KEYS': 'test',
            'BOCHA_BASE_URL': 'http://provider.test', 'BOCHA_API_KEY': 'test',
        }
        spec = importlib.util.spec_from_file_location('_experiment_tool_registry', tools_dir / 'tool.py')
        cls.registry = importlib.util.module_from_spec(spec)
        with patch.dict('os.environ', environment), patch('queue_client.redis_reset_tools'), \
                patch('queue_client.redis_register_tool') as register:
            spec.loader.exec_module(cls.registry)
            spec = importlib.util.spec_from_file_location('_experiment_workspace_tools', tools_dir / 'workspace.py')
            cls.workspace = importlib.util.module_from_spec(spec)
            with patch.dict(sys.modules, {'tools.tool': cls.registry}):
                spec.loader.exec_module(cls.workspace)
        cls.registered_schemas = {c.args[0]: c.args[1] for c in register.call_args_list}
        bundle = build_bundle(model='test-model', main_id='main-123', experience_id='experience-123')
        cls.document = next(x['content'] for x in bundle if x['role'] == 'main')
        cls.iterator = next(x['content'] for x in bundle if x['role'] == 'iterator')

    def setUp(self):
        self.current = {'name': 'runtime-test-main.flow', 'revision': 7,
                        'content': json.dumps(self.document)}

    def response(self, payload, status=200):
        response = Mock(ok=status < 400, status_code=status)
        response.json.return_value = payload
        return response

    def invoke(self, proposal, revision=7):
        # Run the same unified tool node and named typed outputs as the iterator.
        authored = next(n for n in self.iterator['nodes'] if n['id'] == 'evolution_validate')
        node = copy.deepcopy(authored)
        node['_tool_kind'] = 'local'
        arguments = {'file_id': 'main/id', 'revision': revision, 'proposal': proposal}
        node['data_inputs'] = {key: [None, None, value] for key, value in arguments.items()}
        outputs = node['arguments']['outputs']
        node['data_outputs'] = {p['name']: [[1, p['name']]] for p in outputs}
        node['successors'] = {'next': 1}
        target = {'data_inputs': {p['name']: [0, p['name'], None] for p in outputs}}
        with patch.dict(sys.modules, {'tools.tool': self.registry}):
            self.assertEqual(workflow_tool(0, [node, target]), 1)
        return {key: binding[2] for key, binding in target['data_inputs'].items()}

    def test_reference_contracts_match_actual_registered_decorators_and_iterator(self):
        catalog = workspace_tool_catalog()
        self.assertEqual(set(catalog), {n for n in self.registry.tool_handlers if n.startswith('workspace.')})
        for name, entry in catalog.items():
            registered = self.registered_schemas[name]
            self.assertEqual(entry['inputSchema'], registered['function']['parameters'])
            self.assertEqual(entry['outputSchema'], registered['outputSchema'])
            self.assertEqual(entry['handler'], self.registry.tool_handlers[name].__name__)
        declaration = next(t for t in self.iterator['metadata']['tools'] if t['name'] == 'workspace.prepare_main_update')
        registered = catalog[declaration['name']]
        mapping = {'string': 'content', 'integer': 'number'}
        for side, schema in [('input_ports', 'inputSchema'), ('output_ports', 'outputSchema')]:
            expected = {k: mapping[v['type']] for k, v in registered[schema]['properties'].items()}
            self.assertEqual({p['name']: p['type'] for p in declaration[side]}, expected)

    @patch.dict('os.environ', {'WORKSPACE_API_URL': 'http://workspace.test/'})
    def test_actual_dispatch_returns_unchanged_and_sends_acl_identity(self):
        token = current_workflow_process.set(WorkflowProcess(process_id='probe-process', process_type='workflow', status='running', _workspace_token='probe-token'))
        try:
            with patch.object(self.workspace.requests, 'request', return_value=self.response(self.current)) as request:
                result = self.invoke(self.current['content'])
        finally:
            current_workflow_process.reset(token)
        self.assertEqual(result['status'], 'unchanged')
        self.assertEqual(result['revision'], 7)
        self.assertEqual(result['error'], '')
        self.assertEqual(json.loads(result['content']), self.document)
        request.assert_called_once_with('GET', 'http://workspace.test/api/files/main%2Fid',
                                       timeout=(3, 15), headers={'X-AAgent-Process-ID': 'probe-process:probe-token'})

    def test_actual_dispatch_accepts_fenced_candidate_and_preserves_literal_content(self):
        candidate = copy.deepcopy(self.document)
        prompt = next(n for n in candidate['nodes'] if n['id'] == 'prompt')
        prompt['arguments']['append_items'].append({'type': 'fixed', 'value': '\nRemember "put"; path C:\\temp\\apple.'})
        with patch.object(self.workspace.requests, 'request', return_value=self.response(self.current)) as request:
            result = self.invoke('```json\n' + json.dumps(candidate) + '\n```')
        self.assertEqual(result['status'], 'ready', result['error'])
        self.assertEqual(json.loads(result['content']), candidate)
        self.assertEqual(request.call_count, 1)
        self.assertEqual(request.call_args.args[0], 'GET')

    def test_actual_dispatch_rejects_invalid_stale_and_capability_changes_without_writes(self):
        changed = copy.deepcopy(self.document)
        changed['output_ports'].append({'name': 'extra', 'type': 'content'})
        for proposal, revision in [('not json', 7), (self.current['content'], 6), (json.dumps(changed), 7)]:
            with self.subTest(revision=revision, proposal=proposal[:30]), \
                    patch.object(self.workspace.requests, 'request', return_value=self.response(self.current)) as request:
                result = self.invoke(proposal, revision)
                self.assertEqual(result['status'], 'rejected')
                self.assertTrue(result['error'])
                self.assertEqual(result['content'], '')
                self.assertEqual(request.call_count, 1)
                self.assertEqual(request.call_args.args[0], 'GET')

    def test_actual_dispatch_propagates_missing_file_and_acl_errors(self):
        for status, expected in [(404, ValueError), (403, RuntimeError)]:
            with self.subTest(status=status), \
                    patch.object(self.workspace.requests, 'request', return_value=self.response({'error': 'denied or missing'}, status)) as request:
                with self.assertRaises(expected):
                    self.invoke(self.current['content'])
                self.assertEqual(request.call_count, 1)

    @patch.dict('os.environ', {'WORKSPACE_API_URL': 'http://workspace.test/'})
    def test_registered_recovery_tool_uses_encoded_file_ids_and_returns_structured_versions(self):
        responses = [self.response({'content': 'same baseline'}), self.response({'content': 'same baseline'})]
        with patch.object(self.workspace.requests, 'request', side_effect=responses) as request:
            result = self.registry.execute_tool('recovery', 'workspace.get_file_recovery_plan',
                {'file_id': 'main/id', 'stable_file_id': 'stable/id', 'checkpoint_seq': 0}, preserve_result=True)
        self.assertEqual(result, {'versions': []})
        self.assertEqual([call.args[:2] for call in request.call_args_list], [
            ('GET', 'http://workspace.test/api/files/main%2Fid'),
            ('GET', 'http://workspace.test/api/files/stable%2Fid')])

    def test_registered_recovery_tool_does_not_mask_a_missing_main(self):
        with patch.object(self.workspace.requests, 'request', return_value=self.response({'error': 'missing'}, 404)) as request:
            with self.assertRaisesRegex(ValueError, 'workspace file not found'):
                self.registry.execute_tool('recovery', 'workspace.get_file_recovery_plan',
                    {'file_id': 'missing-id', 'stable_file_id': 'stable-id', 'checkpoint_seq': 0}, preserve_result=True)
        self.assertEqual(request.call_count, 1)

    def test_missing_real_handler_fails_before_http(self):
        handlers = {k: v for k, v in self.registry.tool_handlers.items() if k != 'workspace.prepare_main_update'}
        with patch.object(self.registry, 'tool_handlers', handlers), \
                patch.object(self.workspace.requests, 'request') as request:
            with self.assertRaisesRegex(ValueError, 'workspace.prepare_main_update'):
                self.invoke(self.current['content'])
        request.assert_not_called()


if __name__ == '__main__':
    unittest.main()
