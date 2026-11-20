"""Function contracts, invocation isolation, and durable scheduler stack coverage."""
import copy
import json
import unittest

import main
import test_process_workflows as support
from workflow_validator import validate_workflow, WorkflowValidationError
from workflow_parser import parse_workflow
from workflow_nodes import propagate_workflow_output

PORTS = support.PORTS
edge = support.edge


def function_document(nested=False, wait=False, subprocess=False):
    doc = support.document('root')
    doc['input_ports'] = copy.deepcopy(PORTS)
    doc['output_ports'] = copy.deepcopy(PORTS)
    doc['metadata']['functions'] = []
    functions = ['A', 'B'] if nested else ['A']
    doc['nodes'].insert(1, {'id': 'callA', 'type': 'function_call', 'arguments': {'function_id': 'A'}})
    doc['connections'] = [edge('in', 'callA'), edge('callA', 'out'),
                          edge('in', 'callA', 'workflow:text', 'function:text', 'content'),
                          edge('callA', 'out', 'function:text', 'workflow:text', 'content')]
    for fid in functions:
        doc['metadata']['functions'].append({'id': fid, 'name': fid, 'input_ports': copy.deepcopy(PORTS), 'output_ports': copy.deepcopy(PORTS)})
        doc['nodes'] += [{'id': fid + 'in', 'type': 'function_input', 'function_id': fid},
                         {'id': fid + 'out', 'type': 'function_output', 'function_id': fid}]
        previous = source = fid + 'in'
        if fid == 'A' and nested:
            doc['nodes'].append({'id': 'callB', 'type': 'function_call', 'arguments': {'function_id': 'B'}})
            doc['connections'] += [edge(previous, 'callB'), edge(source, 'callB', 'function:text', 'function:text', 'content')]
            previous = source = 'callB'
        elif wait or subprocess:
            kind = 'spawn_and_wait_subprocess' if subprocess else 'read_terminal_queue'
            n = {'id': fid + 'wait', 'type': kind}
            if subprocess:
                n.update(arguments={'workflow_file': 'child.flow'}, input_ports=PORTS, output_ports=PORTS)
                doc['subprocess_workflow_files'] = [{'name': 'child.flow', 'input_ports': PORTS, 'output_ports': PORTS}]
            doc['nodes'].append(n)
            doc['connections'].append(edge(previous, n['id']))
            previous = n['id']
            if subprocess:
                doc['connections'].append(edge(source, previous, 'function:text', 'workflow:text', 'content'))
                source = previous
        doc['connections'] += [edge(previous, fid + 'out'), edge(source, fid + 'out',
                                'workflow:text' if subprocess and source.endswith('wait') else 'function:text', 'function:text', 'content')]
    from test_support import json_subprocess_fixture
    return json_subprocess_fixture(doc)


class FunctionContractsTest(unittest.TestCase):
    def test_recursive_calls_are_rejected(self):
        doc = function_document(nested=True)
        doc['nodes'].append({'id': 'back', 'type': 'function_call', 'function_id': 'B', 'arguments': {'function_id': 'A'}})
        next(e for e in doc['connections'] if e['fromId'] == 'Bin' and e['type'] == 'control')['toId'] = 'back'
        doc['connections'].append(edge('back', 'Bout'))
        with self.assertRaisesRegex(WorkflowValidationError, 'recursive function call'):
            validate_workflow(doc)

    def test_function_requires_entry_and_exit(self):
        for kind, message in [('function_input', 'exactly one'), ('function_output', 'at least one')]:
            doc = function_document()
            doc['nodes'] = [n for n in doc['nodes'] if n['type'] != kind]
            doc['connections'] = [e for e in doc['connections'] if e['fromId'] not in {'Ain', 'Aout'} and e['toId'] not in {'Ain', 'Aout'}]
            with self.assertRaisesRegex(WorkflowValidationError, message):
                validate_workflow(doc)

    def test_nested_document_is_not_mutated(self):
        doc = function_document(nested=True)
        before = copy.deepcopy(doc)
        validate_workflow(doc)
        graph = parse_workflow(doc)
        self.assertEqual(doc, before)
        self.assertNotIn('function_id', next(n for n in graph if n['id'] == 'callB'))

    def test_body_membership_is_inferred_and_legacy_labels_are_discarded(self):
        doc = function_document(nested=True, wait=True)
        for node in doc['nodes']:
            if node['type'] not in {'function_input', 'function_output'}:
                node['function_id'] = 'obsolete_owner'
        before = copy.deepcopy(doc)
        validate_workflow(doc)
        graph = parse_workflow(doc)
        self.assertEqual(doc, before)
        self.assertTrue(all('function_id' not in node for node in graph
                            if node['type'] not in {'function_input', 'function_output'}))

    def test_dfs_rejects_cross_function_control_flow(self):
        doc = function_document(nested=True)
        next(e for e in doc['connections'] if e['fromId'] == 'Ain' and e['type'] == 'control')['toId'] = 'Bin'
        with self.assertRaisesRegex(WorkflowValidationError, 'crosses function boundary'):
            validate_workflow(doc)

    def test_dfs_rejects_shared_body_nodes(self):
        doc = function_document(nested=True)
        next(e for e in doc['connections'] if e['fromId'] == 'Bin' and e['type'] == 'control')['toId'] = 'callB'
        with self.assertRaisesRegex(WorkflowValidationError, 'shared across function boundary'):
            validate_workflow(doc)

    def test_invalid_declarations_and_boundaries(self):
        mutations = [
            (lambda d: d['metadata']['functions'].append(copy.deepcopy(d['metadata']['functions'][0])), 'duplicate'),
            (lambda d: d['metadata']['functions'][0]['input_ports'].append(copy.deepcopy(PORTS[0])), 'duplicate'),
            (lambda d: d['nodes'].append({'id': 'second', 'type': 'function_input', 'function_id': 'A'}), 'control ports|exactly one'),
            (lambda d: d['nodes'].append({'id': 'orphan', 'type': 'function_input'}), 'must belong|required property'),
            (lambda d: d['nodes'][1]['arguments'].update(function_id='unknown'), 'unknown function'),
            (lambda d: d['connections'].append(edge('in', 'Aout', 'workflow:text', 'function:text', 'content')), 'crosses function boundary'),
            (lambda d: d['connections'].append(edge('Ain', 'out', 'function:text', 'workflow:text', 'content')), 'crosses function boundary'),
        ]
        for mutate, error in mutations:
            with self.subTest(error=error):
                doc = function_document()
                mutate(doc)
                with self.assertRaisesRegex(WorkflowValidationError, error):
                    validate_workflow(doc)

    def test_input_and_output_same_name_different_types(self):
        doc = function_document()
        doc['metadata']['functions'][0]['output_ports'] = [{'name': 'text', 'type': 'number'}]
        with self.assertRaisesRegex(WorkflowValidationError, 'requires number'):
            validate_workflow(doc)

    def test_function_has_independent_lifecycle(self):
        doc = function_document()
        doc['nodes'].append({'id': 'router', 'type': 'router', 'function_id': 'A', 'arguments': {'branches': [{'id': 'yes', 'name': 'yes'}]}})
        doc['nodes'].append({'id': 'Aout2', 'type': 'function_output', 'function_id': 'A'})
        doc['connections'] = [e for e in doc['connections'] if not (e['fromId'] == 'Ain' and e['type'] == 'control')]
        doc['connections'] += [edge('Ain', 'router'), edge('Ain', 'router', 'function:text', 'content-in', 'content'),
                               edge('router', 'Aout', 'yes'), edge('router', 'Aout2', 'branch$others'),
                               edge('Ain', 'Aout2', 'function:text', 'function:text', 'content')]
        validate_workflow(doc)
        doc['nodes'].append({'id': 'local', 'type': 'construct_content', 'function_id': 'A',
                             'arguments': {'append_items': [{'type': 'fixed', 'value': 'branch-local'}]}})
        next(e for e in doc['connections'] if e['fromId'] == 'router' and e['fromPortId'] == 'yes')['toId'] = 'local'
        doc['connections'].append(edge('local', 'Aout'))
        doc['connections'] = [e for e in doc['connections'] if not (e['toId'] == 'Aout2' and e['type'] == 'content')]
        doc['connections'].append(edge('local', 'Aout2', 'content-out', 'function:text', 'content'))
        with self.assertRaisesRegex(WorkflowValidationError, 'crosses lifecycle boundary'):
            validate_workflow(doc)


class FunctionProcessTest(unittest.TestCase):
    setUp = support.ProcessWorkflowTest.setUp
    start = support.ProcessWorkflowTest.start
    drain = support.ProcessWorkflowTest.drain
    send = support.ProcessWorkflowTest.send
    workflows = support.ProcessWorkflowTest.workflows

    def test_zero_argument_and_zero_result_function(self):
        doc = function_document()
        doc['metadata']['functions'][0].update(input_ports=[], output_ports=[])
        doc['connections'] = [e for e in doc['connections'] if e['type'] == 'control']
        doc['connections'].append(edge('in', 'out', 'workflow:text', 'workflow:text', 'content'))
        process = self.start(doc)
        self.drain()
        final = main.read_process(process['process_id'])
        self.assertEqual(final['status'], 'completed', final.get('error'))
        self.assertEqual(final['result'], {'text': 'hello'})

    def test_function_can_execute_its_own_loop(self):
        doc = function_document()
        doc['input_ports'][0]['type'] = 'list-content'
        doc['nodes'][0]['workflowPorts'][0]['type'] = 'list-content'
        doc['metadata']['functions'][0]['input_ports'][0]['type'] = 'list-content'
        doc['nodes'] += [
            {'id': 'inner', 'type': 'foreach', 'function_id': 'A', 'arguments': {'item_type': 'content'}},
            {'id': 'body', 'type': 'construct_content', 'function_id': 'A', 'arguments': {'append_items': [{'type': 'fixed', 'value': 'body'}]}},
            {'id': 'done', 'type': 'construct_content', 'function_id': 'A', 'arguments': {'append_items': [{'type': 'fixed', 'value': 'done'}]}},
        ]
        doc['connections'] = [e for e in doc['connections'] if e['fromId'] != 'Ain']
        next(e for e in doc['connections'] if e['fromId'] == 'in' and e['type'] == 'content')['type'] = 'list-content'
        doc['connections'] += [edge('Ain', 'inner'), edge('Ain', 'inner', 'function:text', 'list-in', 'list-content'),
                               edge('inner', 'body', 'loop-out'), edge('body', 'inner', into='loop-in'),
                               edge('inner', 'done'), edge('done', 'Aout'), edge('done', 'Aout', 'content-out', 'function:text', 'content')]
        process = self.start(doc, inputs={'text': ['a', 'b']})
        self.drain()
        final = main.read_process(process['process_id'])
        self.assertEqual(final['status'], 'completed', final.get('error'))
        self.assertEqual(final['result'], {'text': 'done'})
        self.assertEqual(sum(t['node_id'] == 'body' for t in final['node_trace']), 2)

    def test_structs_can_cross_function_interfaces(self):
        doc = function_document()
        doc['metadata']['structs'] = [{'id': 'Record', 'name': 'Record', 'color': '#3976A8', 'fields': []}]
        for side in ['input_ports', 'output_ports']:
            doc['metadata']['functions'][0][side] = [{'name': 'value', 'type': 'struct:Record'}]
        doc['nodes'] += [
            {'id': 'make', 'type': 'construct_struct', 'arguments': {'struct_id': 'Record'}, 'dataInputPorts': []},
            {'id': 'json', 'type': 'struct_to_json', 'arguments': {'value_type': 'struct:Record'}},
        ]
        doc['connections'] = [edge('in', 'make'), edge('make', 'callA'), edge('callA', 'json'), edge('json', 'out'),
                               edge('make', 'callA', 'struct-out', 'function:value', 'struct:Record'),
                               edge('callA', 'json', 'function:value', 'value-in', 'struct:Record'),
                               edge('json', 'out', 'content-out', 'workflow:text', 'content'),
                               edge('Ain', 'Aout'), edge('Ain', 'Aout', 'function:value', 'function:value', 'struct:Record')]
        process = self.start(doc)
        self.drain()
        final = main.read_process(process['process_id'])
        self.assertEqual(final['status'], 'completed', final.get('error'))
        self.assertEqual(final['result'], {'text': '{}'})

    def test_loop_calls_branching_function_with_fresh_arguments(self):
        doc = function_document(nested=True)
        doc['input_ports'].append({'name': 'items', 'type': 'list-content'})
        doc['nodes'][0]['workflowPorts'].append({'id': 'workflow:items', 'name': 'items', 'type': 'list-content'})
        doc['nodes'] += [{'id': 'loop', 'type': 'foreach', 'arguments': {'item_type': 'content'}},
                         {'id': 'print', 'type': 'output_to_terminal'},
                         {'id': 'branch', 'type': 'router', 'function_id': 'B', 'arguments': {'branches': [{'id': 'one', 'name': 'one'}]}},
                         {'id': 'Bsecond', 'type': 'function_output', 'function_id': 'B'}]
        doc['connections'] = [e for e in doc['connections'] if e['fromId'] not in {'in', 'callA', 'Bin'}]
        doc['connections'] += [edge('in', 'loop'), edge('loop', 'callA', 'loop-out'), edge('callA', 'print'),
                               edge('print', 'loop', into='loop-in'), edge('loop', 'out'),
                               edge('in', 'loop', 'workflow:items', 'list-in', 'list-content'),
                               edge('loop', 'callA', 'item-out', 'function:text', 'content'),
                               edge('callA', 'print', 'function:text', 'content-in', 'content'),
                               edge('in', 'out', 'workflow:text', 'workflow:text', 'content'),
                               edge('Bin', 'branch'), edge('Bin', 'branch', 'function:text', 'content-in', 'content'),
                               edge('branch', 'Bout', 'one'), edge('branch', 'Bsecond', 'branch$others'),
                               edge('Bin', 'Bout', 'function:text', 'function:text', 'content'),
                               edge('Bin', 'Bsecond', 'function:text', 'function:text', 'content')]
        process = self.start(doc, inputs={'text': 'parent unchanged', 'items': ['one', 'two']})
        self.drain()
        final = main.read_process(process['process_id'])
        self.assertEqual(final['status'], 'completed', final.get('error'))
        self.assertEqual(final['result'], {'text': 'parent unchanged'})
        self.assertEqual([call.args[0] for call in self.output.call_args_list], ['one', 'two'])
        branch_returns = [t['node_id'] for t in final['node_trace'] if t['node_type'] == 'function_output' and t['function_id'] == 'B']
        self.assertEqual(branch_returns, ['Bout', 'Bsecond'])
        call_ids = {}
        for fid in ('A', 'B'):
            entries = [t for t in final['node_trace'] if t['node_id'] == fid + 'in']
            exits = [t for t in final['node_trace'] if t['node_type'] == 'function_output' and t['function_id'] == fid]
            call_ids[fid] = {t['function_call_id'] for t in entries}
            self.assertEqual(len(call_ids[fid]), 2)
            self.assertEqual({t['function_call_id'] for t in exits}, call_ids[fid])
        self.assertTrue(call_ids['A'].isdisjoint(call_ids['B']))

        # A direct branch in the enclosing loop is still forbidden.
        bad = copy.deepcopy(doc)
        next(n for n in bad['nodes'] if n['id'] == 'print').update(type='router', arguments={'branches': []})
        next(e for e in bad['connections'] if e['fromId'] == 'print')['fromPortId'] = 'branch$others'
        bad['connections'] = [e for e in bad['connections'] if e['toId'] != 'print' or e['type'] == 'control']
        with self.assertRaisesRegex(WorkflowValidationError, 'branching control flow'):
            validate_workflow(bad)

    def test_nested_calls_return_through_serialized_frames(self):
        doc = function_document(nested=True)
        doc['metadata']['functions'][0]['name'] = 'Outer function'
        doc['metadata']['functions'][1]['name'] = 'Inner function'
        process = self.start(doc, text='nested')
        records = self.drain()
        final = main.read_process(process['process_id'])
        self.assertEqual(final['status'], 'completed', final.get('error'))
        self.assertEqual(final['result'], {'text': 'nested'})
        self.assertEqual(final['function_stack'], [])
        self.assertTrue(any(len(p.get('function_stack', [])) == 2 for p in records))
        function_traces = [t for t in final['node_trace'] if t.get('function_id')]
        ids = {}
        for fid, name in [('A', 'Outer function'), ('B', 'Inner function')]:
            traces = [t for t in function_traces if t['function_id'] == fid]
            self.assertTrue(traces)
            self.assertEqual({t['function_name'] for t in traces}, {name})
            ids[fid] = {t['function_call_id'] for t in traces}
            self.assertEqual(len(ids[fid]), 1)
            self.assertRegex(next(iter(ids[fid])), r'^[0-9a-f]{32}$')
        self.assertTrue(ids['A'].isdisjoint(ids['B']))
        self.assertFalse(any('function_call_id' in t for t in final['node_trace']
                             if t['node_id'] in {'in', 'callA', 'out'}))
        self.assertEqual(len(self.workflows()), 1)

    def test_wait_inside_nested_function_survives_resume(self):
        process = self.start(function_document(nested=True, wait=True))
        self.drain()
        waiting = main.read_process(process['process_id'])
        self.assertEqual(waiting['status'], 'blocked', waiting.get('error'))
        self.assertEqual(waiting['active_function_id'], 'B')
        self.assertEqual(len(waiting['function_stack']), 2)
        inner_call_id = waiting['active_function_call_id']
        outer_call_id = waiting['function_stack'][-1]['function_call_id']
        self.assertNotEqual(inner_call_id, outer_call_id)
        self.send(waiting)
        self.drain()
        final = main.read_process(process['process_id'])
        self.assertEqual(final['status'], 'completed', final.get('error'))
        self.assertEqual(final['result'], {'text': 'hello'})
        for fid, call_id in [('A', outer_call_id), ('B', inner_call_id)]:
            traces = [t for t in final['node_trace'] if t.get('function_id') == fid]
            self.assertEqual({t['function_call_id'] for t in traces}, {call_id})

    def test_subprocess_inside_nested_function(self):
        self.documents['child.flow'] = support.document('child')
        process = self.start(function_document(nested=True, subprocess=True))
        self.drain()
        final = main.read_process(process['process_id'])
        self.assertEqual(final['status'], 'completed', final.get('error'))
        self.assertEqual(final['result'], {'text': 'hello'})
        self.assertEqual(len(self.workflows()), 2)

    def test_template_has_no_runtime_data(self):
        graph = parse_workflow(function_document())
        graph[0]['_foreach_items'] = ['stale']
        propagate_workflow_output(graph, graph[0], 'workflow:text', 'old')
        template = main._function_template(graph)
        self.assertNotIn('_foreach_items', template[0])
        self.assertEqual(next(n for n in template if n['id'] == 'Ain')['_function_name'], 'A')
        for node in template:
            self.assertTrue(all(slot[2] is None for slot in node['data_inputs'].values()))
        self.assertEqual(graph[1]['data_inputs']['function:text'][2], 'old')


if __name__ == '__main__':
    unittest.main()
