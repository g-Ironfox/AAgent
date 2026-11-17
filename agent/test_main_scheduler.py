import unittest
from unittest.mock import Mock, patch

import main


class SchedulerTest(unittest.TestCase):
    @patch('main.get_connection')
    @patch('main.write_process')
    @patch('main.read_process')
    def test_block_process_persists_process_event_reference(
        self, read_process, write_process, get_connection
    ):
        process = {'process_id': 'p1', 'status': 'ready'}
        read_process.return_value = process
        client = Mock()
        get_connection.return_value = client

        wait_for = {'kind': 'terminal_message', 'process_id': 'terminal-p1'}
        result = main.block_process('p1', wait_for)

        self.assertEqual(result['status'], 'blocked')
        self.assertEqual(result['wait_for'], wait_for)
        write_process.assert_called_once_with(process)
        client.lrem.assert_called_once_with(main.READY_PROCESSES, 0, 'p1')
        client.sadd.assert_called_once_with(main.BLOCKED_PROCESSES, 'p1')

    @patch('main.get_connection')
    @patch('main.write_process')
    @patch('main.read_process')
    def test_wake_process_requires_matching_source_process_and_kind(
        self, read_process, write_process, get_connection
    ):
        wait_for = {'kind': 'terminal_message', 'process_id': 'terminal-p1'}
        process = {'process_id': 'p1', 'status': 'blocked', 'wait_for': wait_for}
        read_process.return_value = process
        client = Mock()
        get_connection.return_value = client

        result = main.wake_process('p1', 'other-terminal', 'terminal_message')

        self.assertEqual(result['status'], 'blocked')
        self.assertEqual(result['wait_for'], wait_for)
        write_process.assert_not_called()
        client.lpush.assert_not_called()

    @patch('main.get_connection')
    @patch('main.write_process')
    @patch('main.read_process')
    def test_wake_process_clears_matching_wait_for(
        self, read_process, write_process, get_connection
    ):
        process = {
            'process_id': 'p1',
            'status': 'blocked',
            'wait_for': {'kind': 'terminal_message', 'process_id': 'terminal-p1'},
        }
        read_process.return_value = process
        client = Mock()
        get_connection.return_value = client

        result = main.wake_process('p1', 'terminal-p1', 'terminal_message')

        self.assertEqual(result['status'], 'ready')
        self.assertIsNone(result['wait_for'])
        write_process.assert_called_once_with(process)
        client.lpush.assert_called_once_with(main.READY_PROCESSES, 'p1')

    @patch('main._enqueue_ready_process')
    @patch('main._initialize_process_timing')
    @patch('main.write_process')
    def test_create_process_creates_passive_terminal_process(
        self, write_process, initialize_timing, enqueue
    ):
        process = {'process_id': 'p1', 'workflow': '[]'}

        result = main.create_process(process)

        self.assertEqual(result['process_type'], 'workflow')
        self.assertEqual(result['status'], 'ready')
        terminal_process_id = result['terminal_process_id']
        self.assertTrue(result['start_time'])
        self.assertEqual(write_process.call_count, 2)
        terminal = write_process.call_args_list[1].args[0]
        self.assertEqual(terminal['process_id'], terminal_process_id)
        self.assertEqual(terminal['process_type'], 'terminal')
        self.assertEqual(terminal['parent_process_id'], 'p1')
        self.assertEqual(terminal['status'], 'waiting_for_input')
        initialize_timing.assert_called_once_with(process)
        enqueue.assert_called_once_with('p1')

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

    @patch('main.get_connection')
    @patch('main.Executor')
    def test_schedule_once_requeues_runnable_process(self, executor, get_connection):
        client = Mock()
        client.brpop.return_value = (main.READY_PROCESSES, 'p1')
        get_connection.return_value = client
        executor.return_value = {'process_id': 'p1', 'status': 'ready'}

        result = main.schedule_once(timeout=2)

        self.assertEqual(result['status'], 'ready')
        executor.assert_called_once_with('p1')
        client.lpush.assert_called_once_with(main.READY_PROCESSES, 'p1')
        client.srem.assert_any_call(main.BLOCKED_PROCESSES, 'p1')

    @patch('main.get_connection')
    @patch('main.Executor')
    def test_schedule_once_moves_blocked_process_to_blocked_table(
        self, executor, get_connection
    ):
        client = Mock()
        client.brpop.return_value = (main.READY_PROCESSES, 'p1')
        get_connection.return_value = client
        executor.return_value = {'process_id': 'p1', 'status': 'blocked'}

        result = main.schedule_once()

        self.assertEqual(result['status'], 'blocked')
        client.sadd.assert_called_once_with(main.BLOCKED_PROCESSES, 'p1')
        client.lpush.assert_not_called()

    @patch('main.get_connection')
    @patch('main.Executor')
    def test_schedule_once_does_not_reschedule_completed_process(
        self, executor, get_connection
    ):
        client = Mock()
        client.brpop.return_value = (main.READY_PROCESSES, 'p1')
        get_connection.return_value = client
        executor.return_value = {'process_id': 'p1', 'status': 'completed'}

        main.schedule_once()

        client.srem.assert_called_once_with(main.BLOCKED_PROCESSES, 'p1')
        client.lpush.assert_not_called()

    @patch('main.get_connection')
    def test_schedule_once_returns_when_queue_is_empty(self, get_connection):
        client = Mock()
        client.brpop.return_value = None
        get_connection.return_value = client

        self.assertIsNone(main.schedule_once(timeout=1))
        client.brpop.assert_called_once_with(main.READY_PROCESSES, timeout=1)


if __name__ == '__main__':
    unittest.main()
