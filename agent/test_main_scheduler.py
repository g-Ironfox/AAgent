import json
import unittest
from unittest.mock import Mock, patch

import main


class SchedulerTest(unittest.TestCase):
    @patch('main._sync_process_observability')
    @patch('main.get_connection')
    @patch('main.write_process')
    @patch('main.read_process')
    def test_block_process_persists_process_event_reference(
        self, read_process, write_process, get_connection, sync
    ):
        process = {'process_id': 'p1', 'status': 'ready'}
        read_process.return_value = process
        client = Mock()
        get_connection.return_value = client

        wait_for = {'kind': 'terminal_message', 'process_id': 'terminal-p1'}
        result = main.block_process('p1', wait_for)

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
        process = {'process_id': 'p1', 'workflow': '[]', 'terminal_id': 'public-terminal'}

        result = main.create_process(process)

        self.assertEqual(result['process_type'], 'workflow')
        self.assertEqual(result['status'], 'ready')
        terminal_process_id = result['terminal_process_id']
        self.assertTrue(result['start_time'])
        terminal = publish.call_args.args[2]
        publish.assert_called_once_with(get_connection.return_value, process, terminal)
        self.assertEqual(terminal['process_id'], terminal_process_id)
        self.assertEqual(terminal['process_type'], 'terminal')
        self.assertEqual(terminal['parent_process_id'], 'p1')
        self.assertEqual(terminal['terminal_id'], 'public-terminal')
        self.assertNotEqual(terminal['process_id'], terminal['terminal_id'])
        self.assertEqual(terminal['status'], 'waiting_for_input')
        initialize_timing.assert_called_once_with(process)

    @patch('main.get_connection')
    @patch('main.write_process')
    @patch('main.read_process')
    def test_parent_cleanup_terminates_and_unindexes_terminal(
        self, read_process, write_process, get_connection
    ):
        parent = {'process_id': 'p1', 'terminal_process_id': 'terminal-p1'}
        terminal = {
            'process_id': 'terminal-p1',
            'process_type': 'terminal',
            'parent_process_id': 'p1',
            'status': 'waiting_for_input',
        }
        read_process.return_value = terminal
        client = Mock()
        get_connection.return_value = client

        main._terminate_terminal_process(parent)

        self.assertEqual(terminal['status'], 'terminated')
        self.assertIsNone(terminal['wait_for'])
        self.assertTrue(terminal['finished_at'])
        write_process.assert_called_once_with(terminal)
        client.lrem.assert_called_once_with(
            main.READY_PROCESSES, 0, 'terminal-p1'
        )
        client.srem.assert_called_once_with(
            main.BLOCKED_PROCESSES, 'terminal-p1'
        )

    @patch('main.get_event_connection')
    @patch('main.get_connection')
    @patch('main.Executor')
    def test_schedule_once_delegates_state_commit_to_executor(self, executor, get_connection, get_events):
        client = get_connection.return_value
        events = get_events.return_value
        client.rpop.return_value = 'p1'
        events.rpop.return_value = None
        for status in ('ready', 'blocked', 'completed', 'failed', 'terminated'):
            executor.return_value = {'process_id': 'p1', 'status': status}
            self.assertEqual(main.schedule_once(timeout=2)['status'], status)
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
        process = {'process_id': 'p1'}
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
    @patch('main.wake_process_record')
    def test_terminal_event_is_applied_by_runtime(self, wake, sync):
        client = Mock()
        client.hget.return_value = json.dumps({
            'process_id': 'terminal-1',
            'process_type': 'terminal',
            'parent_process_id': 'workflow-1',
        })
        client.hget.return_value = 'terminal-1'
        event = {'type': 'terminal_message', 'terminal_id': 'public-terminal'}
        client.hget.side_effect = [
            'terminal-1',
            json.dumps({
                'process_id': 'terminal-1',
                'process_type': 'terminal',
                'terminal_id': 'public-terminal',
                'parent_process_id': 'workflow-1',
            }),
        ]

        main.handle_external_event(client, json.dumps(event))

        wake.assert_called_once_with(
            client, 'workflow-1', 'terminal-1', 'terminal_message'
        )

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
