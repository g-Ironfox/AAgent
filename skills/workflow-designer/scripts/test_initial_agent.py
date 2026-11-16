"""Execute the delivered ReAct graphs with real nodes and Context operations.

Only external Redis/model/tool/workspace/logging boundaries are replaced.
"""
from __future__ import annotations

import copy
import json
import types
import unittest
from unittest.mock import Mock, patch

from validate_design import REPO, read_json, validate_design
from workflow_nodes import propagate_workflow_output, run_workflow_map
from workflow_parser import parse_workflow


class MemoryRedis:
    """Redis hash/transaction subset used by workflow_context_repository."""

    def __init__(self):
        self.hashes = {}
        self.list_writes = []

    def eval(self, script, numkeys, key, *args):
        if key in self.hashes:
            return 0
        self.hashes[key] = dict(zip(args[:-1:2], args[1:-1:2]))
        return 1

    def delete(self, *keys):
        for key in keys:
            self.hashes.pop(key, None)

    def pipeline(self):
        storage = self

        class Pipeline:
            def __init__(self):
                self.pending = []

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def watch(self, key):
                pass

            def hgetall(self, key):
                return dict(storage.hashes.get(key, {}))

            def multi(self):
                pass

            def hset(self, key, mapping):
                self.pending.append((key, mapping))

            def expire(self, key, ttl):
                pass

            def execute(self):
                for key, mapping in self.pending:
                    storage.hashes[key].update(mapping)
                    if storage.hashes[key]['value_type'] == 'list-content':
                        storage.list_writes.append(json.loads(mapping['value']))
                self.pending.clear()
                return []

        return Pipeline()


def tool_call(index, name='tavily_search'):
    arguments = {'keyword': f'query-{index}'} if name == 'tavily_search' else {'title': f'document-{index}'}
    return {'id': f'call-{index}', 'type': 'function',
            'function': {'name': name, 'arguments': json.dumps(arguments)}}


def tool_schema(name):
    return {'type': 'function', 'function': {'name': name, 'description': name,
            'parameters': {'type': 'object', 'properties': {}}}}


class InitialAgentExecutionTest(unittest.TestCase):
    def setUp(self):
        self.design = read_json(REPO / 'workflow-design' / 'executor-agent.design.json')
        validate_design(self.design)
        self.redis = MemoryRedis()
        self.messages_seen = []
        self.tools_seen = []
        self.checkpoints_seen = []

    def execute(self, responses, *, remote_error=None):
        documents = {i['filename']: i['workflow'] for i in self.design['workflows']}
        main = documents[self.design['entrypoint']]
        graph = parse_workflow(main)
        start = next(i for i, n in enumerate(graph) if n['type'] == 'input')
        origin = {'version': '1.1', 'event_type': 'user',
                  'payload': {'content': 'Investigate this task "quoted"\nwith a newline'}}
        graph[start]['_workflow_input_values'] = {'origin': origin}
        propagate_workflow_output(graph, graph[start], 'workflow:origin', origin)
        iterator = iter(responses)

        def chat(messages, model, *, tools, think):
            self.assertEqual(model, '6aba33cb2d499f6a57d08bc3')
            self.assertFalse(think)
            self.assertEqual({t['function']['name'] for t in tools}, {
                'tavily_search', 'documents.query_by_name', 'documents.query_by_id',
                'workspace.list_files', 'workspace.get_file', 'workspace.create_file',
                'workspace.update_file', 'workspace.delete_file',
                'workspace.list_checkpoints', 'workspace.checkpoint_tree',
                'workspace.get_parent_checkpoint', 'workspace.checkpoint_diff'})
            self.messages_seen.append(copy.deepcopy(messages))
            response = next(iterator)  # Any unnecessary extra model call fails.
            if isinstance(response, Exception):
                raise response
            return response

        def execute_local(node_id, name, arguments, *, preserve_result):
            self.assertTrue(preserve_result)
            if name == 'workspace.create_checkpoint':
                self.checkpoints_seen.append(copy.deepcopy(arguments))
                return {'seq': 5, 'type': 'workspace.checkpoint', 'data': {'name': arguments['name']}}
            self.tools_seen.append((name, copy.deepcopy(arguments)))
            return {'result': 'local evidence', 'query': arguments}

        def execute_remote(name, arguments, *args):
            self.tools_seen.append((name, copy.deepcopy(arguments)))
            if remote_error:
                raise remote_error
            return {'result': 'remote evidence', 'query': arguments}

        llm = types.ModuleType('llm')
        llm.chat_with_model = Mock(side_effect=chat)
        registry = types.ModuleType('tools.tool')
        local_names = ['tavily_search', 'workspace.list_files', 'workspace.get_file',
                       'workspace.create_file', 'workspace.update_file', 'workspace.delete_file',
                       'workspace.create_checkpoint', 'workspace.list_checkpoints', 'workspace.checkpoint_tree',
                       'workspace.get_parent_checkpoint', 'workspace.checkpoint_diff']
        registry.registered_tools = [tool_schema(name) for name in local_names]
        registry.tool_handlers = dict.fromkeys(local_names, True)
        registry.execute_tool = execute_local
        with patch.dict('sys.modules', {'llm': llm, 'tools.tool': registry}), \
             patch('workflow_parser._read_workspace_workflow_by_name',
                   side_effect=lambda name: copy.deepcopy(documents[name])), \
             patch('workflow_context_repository.get_connection', return_value=self.redis), \
             patch('workflow_run_repository.record_workflow_run'), \
             patch('tool_server_client.get_remote_tool_schemas',
                   side_effect=lambda names: [tool_schema(name) for name in sorted(names)]), \
             patch('tool_server_client.call_remote_tool', side_effect=execute_remote), \
             patch('queue_client.publish_to_queue') as publish:
            try:
                return run_workflow_map(graph, start)
            finally:
                self.assertEqual(self.redis.hashes, {}, 'all invocation Contexts must be cleaned up')
                publish.assert_not_called()

    def test_three_tool_rounds_then_stop_with_the_model_final_answer(self):
        output = self.execute([
            (None, None, [tool_call(1)]),
            ('intermediate text', None, [tool_call(2, 'documents.query_by_name')]),
            (None, None, [tool_call(3)]),
            ('final evidence-based answer', None, []),
        ])
        self.assertEqual(output, {'content': 'final evidence-based answer'})
        self.assertEqual(len(self.messages_seen), 4)
        self.assertEqual(len(self.tools_seen), 3)
        self.assertEqual([len(m) for m in self.messages_seen], [2, 3, 4, 5])
        for index, messages in enumerate(self.messages_seen[1:], 1):
            self.assertIn(f'call-{index}', messages[-1]['content'])
            self.assertEqual(messages[-1]['role'], 'user')
        self.assertTrue(all(len(items) <= 1 for items in self.redis.list_writes))
        self.assertEqual(self.redis.list_writes[-1], [])

    def test_multiple_tools_schedule_exactly_one_next_round(self):
        output = self.execute([
            (None, None, [tool_call(1), tool_call(2, 'documents.query_by_name'), tool_call(3)]),
            ('done', None, []),
        ])
        self.assertEqual(output, {'content': 'done'})
        self.assertEqual(len(self.messages_seen), 2)
        self.assertEqual(len(self.tools_seen), 3)
        self.assertEqual(len(self.messages_seen[1]), 5)
        self.assertTrue(all(len(items) <= 1 for items in self.redis.list_writes))

    def test_zero_tools_returns_first_answer_without_a_summary_call(self):
        self.assertEqual(self.execute([('immediate answer', None, [])]),
                         {'content': 'immediate answer'})
        self.assertEqual(len(self.messages_seen), 1)
        self.assertEqual(self.tools_seen, [])
        self.assertEqual(len(self.checkpoints_seen), 1)
        self.assertEqual(self.redis.list_writes, [[]])

    def test_tool_failure_becomes_an_observation_and_model_can_stop(self):
        output = self.execute([
            (None, None, [tool_call(1, 'documents.query_by_name')]),
            ('explain unavailable evidence', None, []),
        ], remote_error=RuntimeError('temporary remote failure'))
        self.assertEqual(output, {'content': 'explain unavailable evidence'})
        self.assertEqual(len(self.messages_seen), 2)
        self.assertIn('temporary remote failure', self.messages_seen[1][-1]['content'])
        self.assertIn('RuntimeError', self.messages_seen[1][-1]['content'])

    def test_model_failure_aborts_and_cleans_parent_contexts(self):
        with self.assertRaisesRegex(RuntimeError, 'provider unavailable'):
            self.execute([(None, None, [tool_call(1)]), RuntimeError('provider unavailable')])
        self.assertEqual(len(self.messages_seen), 2)

    def test_exported_flows_match_design_and_all_edges_have_unique_ids(self):
        for item in self.design['workflows']:
            with self.subTest(filename=item['filename']):
                native = read_json(REPO / 'workflow-design' / 'flows' / item['filename'])
                self.assertEqual(native, item['workflow'])
                ids = [e['id'] for e in native['connections']]
                self.assertEqual(len(ids), len(set(ids)))
                for n in native['nodes']:
                    self.assertNotIn('?', n['name'])


if __name__ == '__main__':
    unittest.main()
