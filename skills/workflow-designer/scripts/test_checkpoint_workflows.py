"""Exercise checkpoint workflows using the actual local registry and wrappers.

Only HTTP storage, Redis, model, queue and execution-log boundaries are replaced.
"""
from __future__ import annotations

import copy
import importlib.util
import json
import sys
import unittest
from unittest.mock import Mock, patch

from validate_design import REPO, read_json, validate_design
from test_initial_agent import MemoryRedis, tool_schema
from workflow_nodes import propagate_workflow_output, run_workflow_map
from workflow_parser import parse_workflow


class CheckpointWorkflowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tools_dir = REPO / 'agent' / 'tools'
        spec = importlib.util.spec_from_file_location('_checkpoint_registry', tools_dir / 'tool.py')
        cls.registry = importlib.util.module_from_spec(spec)
        env = {'DEEPSEEK_BASE_URL': 'http://test', 'DEEPSEEK_API_KEY': 'test',
               'KIMI_BASE_URL': 'http://test', 'KIMI_API_KEY': 'test', 'ZAI_API_KEY': 'test',
               'TAVILY_API_KEYS': 'test', 'BOCHA_BASE_URL': 'http://test', 'BOCHA_API_KEY': 'test'}
        with patch.dict('os.environ', env), patch('queue_client.redis_reset_tools'), \
             patch('queue_client.redis_register_tool'):
            spec.loader.exec_module(cls.registry)
            spec = importlib.util.spec_from_file_location('_checkpoint_workspace', tools_dir / 'workspace.py')
            cls.workspace = importlib.util.module_from_spec(spec)
            with patch.dict(sys.modules, {'tools.tool': cls.registry}):
                spec.loader.exec_module(cls.workspace)

    def setUp(self):
        self.designs = [read_json(REPO / 'workflow-design' / name) for name in (
            'initial-agent.design.json', 'executor-agent.design.json', 'sidecar.design.json')]
        self.docs = {}
        for design in self.designs:
            validate_design(design)
            self.docs.update({i['filename']: i['workflow'] for i in design['workflows']})
        self.files = {'initial_agent.flow': 'entry', 'task.md': 'before task'}
        self.checkpoints = []
        self.head = 0
        self.api_calls = []
        self.failure_path = None
        self.logs = [{'kind': 'past evidence'}]
        self.redis = MemoryRedis()
        llm = type(sys)('llm')
        self.chat = Mock(return_value=('completed', None, []))
        llm.chat_with_model = self.chat
        self.publish = Mock()
        self.execute_tool = Mock(wraps=self.registry.execute_tool)
        patches = [patch.dict(sys.modules, {'tools.tool': self.registry, 'llm': llm}),
            patch.object(self.registry, 'execute_tool', self.execute_tool),
            patch.object(self.workspace, '_request', side_effect=self.api),
            patch('workflow_context_repository.get_connection', return_value=self.redis),
            patch('workflow_parser._read_workspace_workflow_by_name', side_effect=lambda name: copy.deepcopy(self.docs[name])),
            patch('workflow_run_repository.record_workflow_run'),
            patch('queue_client.publish_to_queue', self.publish),
            patch('tool_server_client.get_remote_tool_schemas', side_effect=lambda names: [tool_schema(n) for n in sorted(names)]),
            patch('tool_server_client.call_remote_tool', side_effect=ValueError('unknown remote tool'))]
        for item in patches:
            item.start()
            self.addCleanup(item.stop)
        self.addCleanup(lambda: self.assertEqual(self.redis.hashes, {}))
        self.addCleanup(self.publish.assert_not_called)

    def api(self, method, path, **kwargs):
        self.api_calls.append((method, path, copy.deepcopy(kwargs)))
        if path == self.failure_path:
            raise RuntimeError('checkpoint API unavailable: ' + path)
        if method == 'POST' and path == '/checkpoints':
            event = {'seq': len(self.checkpoints) + 1, 'type': 'workspace.checkpoint',
                     'timestamp': 'test', 'data': {'name': kwargs['json']['name'],
                     'parent_seq': self.head or None, 'files': copy.deepcopy(self.files)}}
            self.checkpoints.append(copy.deepcopy(event))
            self.head = event['seq']
            return event
        if method == 'GET' and path == '/checkpoints/tree':
            return {'head_seq': self.head or None, 'items': copy.deepcopy(self.checkpoints)}
        if method == 'POST' and path.endswith('/restore'):
            seq = int(path.split('/')[2])
            self.files = copy.deepcopy(self.checkpoints[seq - 1]['data']['files']) if seq else {}
            self.head = seq
            return {'seq': len(self.checkpoints) + 100, 'type': 'workspace.restore',
                    'data': {'checkpoint_seq': seq}}
        raise AssertionError('unexpected workspace request: ' + method + ' ' + path)

    def run_graph(self, name='rsi_sidecar.flow', event=None):
        graph = parse_workflow(copy.deepcopy(self.docs[name]))
        origin = event or {'version': '1.1', 'event_type': 'error',
                           'payload': {'workflow_name': 'initial_agent.flow', 'message': 'executor failed'}}
        start = next(i for i, n in enumerate(graph) if n['type'] == 'input')
        graph[start]['_workflow_input_values'] = {'origin': origin}
        propagate_workflow_output(graph, graph[start], 'workflow:origin', origin)
        return run_workflow_map(graph, start)

    def baseline_and_failure(self):
        self.api('POST', '/checkpoints', json={'name': 'baseline'})
        self.files['task.md'] = 'failed modification'
        self.files['new.md'] = 'created by failed task'
        self.logs.append({'kind': 'failed execution evidence'})

    def test_entry_saves_baseline_before_first_model_call(self):
        def chat(*args, **kwargs):
            self.assertEqual(self.head, 1)
            self.assertEqual(self.checkpoints[0]['data']['files'], self.files)
            names = {tool['function']['name'] for tool in kwargs['tools']}
            self.assertIn('workspace.checkpoint_diff', names)
            self.assertNotIn('workspace.restore_checkpoint', names)
            self.assertNotIn('workspace.create_checkpoint', names)
            return 'completed', None, []
        self.chat.side_effect = chat
        result = self.run_graph('initial_agent.flow', {'version': '1.1', 'event_type': 'user', 'payload': {'content': 'task'}})
        self.assertEqual(result, {'content': 'completed'})
        self.assertEqual(len(self.checkpoints), 1)
        self.assertEqual(self.docs['initial_agent.flow']['name'], 'initial_agent.flow')

    def test_model_failure_then_sidecar_restores_exact_preexecution_files(self):
        before = copy.deepcopy(self.files)
        def failed_model(*args, **kwargs):
            self.files['task.md'] = 'failed modification'
            raise RuntimeError('provider failed after edits')
        self.chat.side_effect = failed_model
        with self.assertRaisesRegex(RuntimeError, 'provider failed'):
            self.run_graph('initial_agent.flow')
        self.logs.append({'kind': 'failed execution evidence'})
        result = self.run_graph()
        self.assertIn('checkpoint', result['content'])
        self.assertEqual(self.files, before)
        self.assertEqual(self.head, 1)
        self.assertEqual(self.checkpoints[1]['data']['files']['task.md'], 'failed modification')
        self.assertEqual(len(self.logs), 2)
        params = {call.args[1]: call.args[2] for call in self.execute_tool.call_args_list}
        self.assertIs(type(params['workspace.get_parent_checkpoint']['seq']), int)
        self.assertIs(type(params['workspace.restore_checkpoint']['seq']), int)
        self.assertEqual(params['workspace.restore_checkpoint']['seq'], 1)

    def test_empty_parent_never_clears_workspace(self):
        before = copy.deepcopy(self.files)
        result = self.run_graph()
        self.assertIn('0', result['content'])
        self.assertEqual(self.files, before)
        self.assertEqual(len(self.checkpoints), 1)
        self.assertFalse(any(path.endswith('/restore') for _, path, _ in self.api_calls))

    def test_null_parent_is_reported_without_restore(self):
        handler = Mock(return_value={'seq': 1, 'parent_seq': None})
        with patch.dict(self.registry.tool_handlers, {'workspace.get_parent_checkpoint': handler}):
            result = self.run_graph()
        self.assertIn('父 checkpoint', result['content'])
        self.assertFalse(any(path.endswith('/restore') for _, path, _ in self.api_calls))

    def test_nonerror_event_does_not_touch_checkpoints(self):
        result = self.run_graph(event={'event_type': 'user', 'payload': {}})
        self.assertIn('error', result['content'])
        self.assertEqual(self.api_calls, [])

    def test_each_api_failure_becomes_output_and_stops_sidecar(self):
        for path, expected_calls in (('/checkpoints', 1), ('/checkpoints/tree', 2), ('/checkpoints/1/restore', 3)):
            with self.subTest(path=path):
                self.checkpoints = []
                self.head = 0
                self.baseline_and_failure()
                self.api_calls = []
                self.failure_path = path
                result = self.run_graph()
                self.assertIn('checkpoint API unavailable', result['content'])
                self.assertEqual(len(self.api_calls), expected_calls)
                self.assertEqual(self.files['task.md'], 'failed modification')
                self.failure_path = None

    def test_exported_flows_match_all_designs_and_use_only_registered_local_tools(self):
        for design in self.designs:
            for item in design['workflows']:
                self.assertEqual(read_json(REPO / 'workflow-design' / 'flows' / item['filename']), item['workflow'])
                self.assertEqual(item['workflow']['schema_version'], '2.0')
                for declaration in item['workflow']['metadata']['tools']:
                    if declaration['kind'] == 'local':
                        self.assertIn(declaration['name'], self.registry.tool_handlers)


if __name__ == '__main__':
    unittest.main()
