"""Fast unit tests; no database, data download or runtime required."""
import unittest
from unittest.mock import Mock, patch
from pydantic import ValidationError

from benchmark_common.models import JobConfig, summarize
from benchmark_common.store import Store
from benchmark_worker.main import Worker
from alfworld_runner.client import TerminalClient


class ContractTests(unittest.TestCase):
    def test_invalid_config(self):
        for value in ({"episodes": 0}, {"episodes": True}, {"max_steps": 0}, {"seed": -1},
                      {"split": "test"}, {"inputs": []}, {"action_timeout": float("inf")},
                      {"workflow_file_id": " "}, {"inputs": {"x": 2**70}}, {"typo": 1}):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                JobConfig.model_validate(dict({"workflow_file_id": "flow"}, **value))

    def test_summary_does_not_hide_errors(self):
        result = summarize([{"success": True, "status": "success"},
                            {"success": False, "status": "error"}], 3)
        self.assertEqual(result, {"requested": 3, "completed": 2, "successes": 1,
                                  "errors": 1, "success_rate": 0.5})

    def test_shutdown_interrupts_action_poll(self):
        client = TerminalClient("http://unused", check=Mock(side_effect=RuntimeError("stop")))
        client.request = Mock()
        try:
            with self.assertRaisesRegex(RuntimeError, "stop"):
                client.action("t", "e", 0, 10)
            client.request.assert_not_called()
        finally:
            client.close()

    def test_dispatch_outage_does_not_interrupt_active_job(self):
        store = Mock()
        store.heartbeat.return_value = True
        store.maintenance.side_effect = RuntimeError("Redis offline")
        worker = Worker(store)
        worker.active_job = "job"
        done = Mock()
        done.wait.side_effect = [False, True]
        with self.assertLogs("benchmark_worker", level="ERROR"):
            worker.keepalive(done)
        self.assertFalse(worker.lease_lost.is_set())

    def test_expired_heartbeat_interrupts_current_job(self):
        store = Mock()
        store.heartbeat.return_value = False
        worker = Worker(store)
        worker.active_job = "job"
        done = Mock()
        done.wait.side_effect = [False, True]
        worker.keepalive(done)
        self.assertTrue(worker.lease_lost.is_set())

    def test_previous_job_heartbeat_does_not_interrupt_next_job(self):
        store = Mock()
        worker = Worker(store)
        worker.active_job = "old"
        def switched(*args, **kwargs):
            worker.active_job = "new"
            return False
        store.heartbeat.side_effect = switched
        done = Mock()
        done.wait.side_effect = [False, True]
        worker.keepalive(done)
        self.assertFalse(worker.lease_lost.is_set())

    def test_duplicate_notification_does_not_execute(self):
        store = Mock()
        store.claim.return_value = None
        worker = Worker(store)
        worker.execute = Mock()
        worker.handle("1-0", {"job_id": "job"})
        worker.execute.assert_not_called()
        store.redis.xack.assert_called_once()

    @patch("benchmark_worker.main.version", return_value="test")
    def test_worker_uses_isolated_terminals_and_persists_trace(self, _):
        store = Mock()
        store.update_running.return_value = True
        env = Mock()
        env.reset.return_value = (["room"], {"extra.gamefile": ["one"]})
        env.step.return_value = (["done"], [1], [True], {"won": [True]})
        client = Mock()
        client.action.return_value = "look"
        worker = Worker(store, env_factory=Mock(return_value=(env, ["one", "two"])),
                        client_factory=Mock(return_value=client))
        worker.execute({"job_id": "job", "config": JobConfig(workflow_file_id="flow", episodes=2).model_dump()})
        self.assertEqual(client.start.call_count, 2)
        terminals = [call.args[1] for call in client.start.call_args_list]
        self.assertEqual(len(set(terminals)), 2)
        directions = [call.args[3]["direction"] for call in store.append.call_args_list]
        self.assertEqual(directions, ["observation", "action", "observation", "result"] * 2)
        self.assertEqual(store.update_running.call_args.args[2]["status"], "completed")
        env.close.assert_called_once()
        client.close.assert_called_once()

    @patch("benchmark_worker.main.version", return_value="test")
    def test_worker_failure_is_fail_fast_and_sends_terminal_done(self, _):
        store = Mock()
        env = Mock()
        env.reset.return_value = (["room"], {"extra.gamefile": ["one"]})
        client = Mock()
        client.action.side_effect = TimeoutError("no action")
        worker = Worker(store, env_factory=Mock(return_value=(env, ["one", "two"])),
                        client_factory=Mock(return_value=client))
        with self.assertLogs("benchmark_worker", level="ERROR"):
            worker.execute({"job_id": "job", "config": JobConfig(workflow_file_id="flow", episodes=2).model_dump()})
        self.assertEqual(client.start.call_count, 1)
        final = client.send.call_args.args[1]
        self.assertTrue(final["done"])
        self.assertEqual(final["reason"], "runner_error")
        fields = store.update_running.call_args.args[2]
        self.assertEqual(fields["status"], "failed")
        self.assertEqual(fields["summary"]["errors"], 1)

    def test_oversized_split_closes_environment(self):
        store = Mock()
        env = Mock()
        worker = Worker(store, env_factory=Mock(return_value=(env, ["one"])))
        with self.assertLogs("benchmark_worker", level="ERROR"):
            worker.execute({"job_id": "job", "config": JobConfig(workflow_file_id="flow", episodes=2).model_dump()})
        self.assertIn("split contains", store.update_running.call_args.args[2]["error"])
        env.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
