import json
import unittest
from unittest.mock import Mock, patch

import main
from process import WorkflowProcess, TerminalProcess


class SchedulerTest(unittest.TestCase):
    @patch('main._sync_process_observability')
    @patch('main.get_connection')
    @patch('main.write_process')
    @patch('main.read_process')
    def test_block_process_persists_process_event_reference(
        self, read_process, write_process, get_connection, sync
    ):
        process = WorkflowProcess(process_id='p1', process_type='workflow', status='ready')
        read_process.return_value = process
        client = Mock()
        get_connection.return_value = client

        wait_for = {'kind': 'terminal_message', 'process_id': 'terminal-p1'}
        result = main.block_process('p1', wait_for).to_record()

        self.assertEqual(result['status'], 'blocked')
        self.assertEqual(result['wait_for'], wait_for)
        self.assertEqual(result['events'][-1]['event'], 'blocked')
        sync.assert_called_once_with(process)
        write_process.assert_called_once_with(process)
        client.lrem.assert_called_once_with(main.READY_PROCESSES, 0, 'p1')
        client.sadd.assert_called_once_with(main.BLOCKED_PROCESSES, 'p1')

    @patch('main.get_connection')
    @patch('main.publish_process_pair')
    @patch('main._initialize_process_timing')
    def test_create_process_creates_passive_terminal_process(
        self, initialize_timing, publish, get_connection
    ):
        process = WorkflowProcess(process_id='p1', process_type='workflow', status='ready', workflow='[]', terminal_id='public-terminal')

        result = main.create_process(process).to_record()

        self.assertEqual(result['process_type'], 'workflow')
        self.assertEqual(result['status'], 'ready')
        terminal_process_id = result['terminal_process_id']
        self.assertTrue(result['start_time'])
        terminal = publish.call_args.args[2]
        publish.assert_called_once_with(get_connection.return_value, process, terminal)
        terminal = terminal.to_record()
        self.assertEqual(terminal['process_id'], terminal_process_id)
        self.assertEqual(terminal['process_type'], 'terminal')
        self.assertEqual(terminal['parent_process_id'], 'p1')
        self.assertEqual(terminal['terminal_id'], 'public-terminal')
        self.assertNotEqual(terminal['process_id'], terminal['terminal_id'])
        self.assertEqual(terminal['status'], 'waiting_for_input')
        initialize_timing.assert_called_once_with(process)

    @patch('main.get_event_connection')
    @patch('main.get_connection')
    @patch('main.Executor')
    def test_schedule_once_delegates_state_commit_to_executor(self, executor, get_connection, get_events):
        client = get_connection.return_value
        events = get_events.return_value
        client.rpop.return_value = 'p1'
        events.rpop.return_value = None
        for status in ('ready', 'blocked', 'completed', 'failed', 'terminated'):
            executor.return_value = WorkflowProcess(process_id='p1', process_type='workflow', status=status)
            self.assertEqual(main.schedule_once(timeout=2).status, status)
        self.assertEqual(executor.call_count, 5)
        executor.assert_called_with('p1')
        client.rpop.assert_called_with(main.READY_PROCESSES)
        client.brpop.assert_not_called()
        events.brpop.assert_not_called()
        client.lpush.assert_not_called()
        client.sadd.assert_not_called()

    @patch('main.get_event_connection')
    @patch('main.get_connection')
    def test_schedule_once_returns_when_queue_is_empty(self, get_connection, get_events):
        client = get_connection.return_value
        events = get_events.return_value
        client.rpop.return_value = None
        events.brpop.return_value = None

        self.assertIsNone(main.schedule_once(timeout=1))
        client.rpop.assert_called_once_with(main.READY_PROCESSES)
        events.brpop.assert_called_once_with(main.EXTERNAL_EVENTS, timeout=1)
        client.brpop.assert_not_called()

    @patch('main.create_process')
    @patch('process_creation.build_workflow_process')
    def test_create_process_event_builds_from_embedded_workflow(
        self, build_process, create_process
    ):
        process = WorkflowProcess(process_id='p1', process_type='workflow', status='ready')
        build_process.return_value = process
        event = {
            'type': 'create_process',
            'workflow_content': '{"schema_version":"2.0"}',
            'workflow_file_id': 'file-1',
            'workflow_name': 'root.flow',
            'workflow_permissions': {
                'runtime': {'read': 2, 'write': 1},
                'required': {'read': 0, 'write': 0},
            },
            'inputs': {'prompt': 'hello'},
            'terminal_id': 'public-terminal',
        }

        main.handle_external_event(Mock(), json.dumps(event))

        build_process.assert_called_once_with(
            {'schema_version': '2.0'}, {'prompt': 'hello'}, 'file-1', 'root.flow',
            'public-terminal', event['workflow_permissions'],
        )
        create_process.assert_called_once_with(process)

    @patch('main._sync_process_observability')
    @patch('main.enqueue_terminal_input')
    def test_terminal_event_buffers_its_content(self, enqueue, sync):
        client = Mock()
        event = {'type': 'terminal_message', 'terminal_id': 'public-terminal', 'content': 'hello'}
        main.handle_external_event(client, json.dumps(event))
        enqueue.assert_called_once_with(client, 'public-terminal', 'hello')
        sync.assert_called_once_with(enqueue.return_value)

    @patch('main.handle_external_event')
    @patch('main.Executor')
    @patch('main.get_connection')
    @patch('main.get_event_connection')
    def test_ready_step_drains_all_pending_external_events(
        self, get_events, get_connection, executor, handle_event
    ):
        client = get_connection.return_value
        events = get_events.return_value
        client.rpop.return_value = 'p1'
        events.rpop.side_effect = ['event-1', 'event-2', None]
        order = []
        executor.side_effect = lambda process_id: order.append(process_id)
        handle_event.side_effect = lambda kernel, event: order.append(event)

        main.schedule_once(timeout=1)

        self.assertEqual(order, ['p1', 'event-1', 'event-2'])
        self.assertEqual(events.rpop.call_count, 3)
        events.rpop.assert_called_with(main.EXTERNAL_EVENTS)
        handle_event.assert_any_call(client, 'event-1')
        handle_event.assert_any_call(client, 'event-2')
        events.brpop.assert_not_called()

    @patch('main.handle_external_event')
    @patch('main.get_connection')
    @patch('main.get_event_connection')
    def test_external_event_wakes_idle_scheduler_and_drains_queue(
        self, get_events, get_connection, handle_event
    ):
        client = get_connection.return_value
        events = get_events.return_value
        client.rpop.return_value = None
        events.brpop.return_value = (main.EXTERNAL_EVENTS, 'event-1')
        events.rpop.side_effect = ['event-2', None]

        self.assertIsNone(main.schedule_once())

        events.brpop.assert_called_once_with(main.EXTERNAL_EVENTS, timeout=0)
        handle_event.assert_any_call(client, 'event-1')
        handle_event.assert_any_call(client, 'event-2')
        client.brpop.assert_not_called()


if __name__ == '__main__':
    unittest.main()
