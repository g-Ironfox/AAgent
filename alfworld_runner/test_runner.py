import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from client import TerminalClient, ProtocolError
from runner import evaluate, run_episode


def output(identifier, content):
    return {"id": identifier, "content": content if isinstance(content, str) else json.dumps(content)}


def action(step=0, episode_id="episode", text="look"):
    return {"type": "action", "episode_id": episode_id, "step": step, "text": text}


class TerminalClientTest(unittest.TestCase):
    def setUp(self):
        self.client = TerminalClient("http://backend", poll_interval=0.001)
        self.addCleanup(self.client.close)
        self.client.request = MagicMock()

    def test_start_waits_for_terminal_before_returning(self):
        self.client.cursor = "previous-episode"
        self.client.request.side_effect = [
            {"status": "queued"}, {"sessions": []},
            {"sessions": [{"terminal_id": "terminal", "status": "open"}]},
        ]
        self.client.start("file-id", "terminal", {"task": "test"}, 1)
        self.assertIsNone(self.client.cursor)
        self.assertEqual(self.client.request.call_args_list[0].kwargs["json"], {
            "workflow_file_id": "file-id", "terminal_id": "terminal", "inputs": {"task": "test"},
        })
        self.assertEqual(self.client.request.call_count, 3)

    def test_closed_startup_is_an_error(self):
        self.client.request.side_effect = [{}, {"sessions": [{
            "terminal_id": "terminal", "status": "closed", "workflow_status": "failed",
        }]}]
        with self.assertRaisesRegex(RuntimeError, "closed during startup"):
            self.client.start("file-id", "terminal", {}, 1)

    def test_action_skips_debug_output_and_does_not_skip_the_rest_of_a_page(self):
        self.client.request.side_effect = [
            {"items": [output("1", "reasoning"), output("2", action()), output("3", action(1))],
             "next_cursor": "3"},
            {"items": [output("3", action(1))], "next_cursor": "3"},
        ]
        self.assertEqual(self.client.action("terminal", "episode", 0, 1), "look")
        self.assertEqual(self.client.cursor, "2")
        self.assertEqual(self.client.action("terminal", "episode", 1, 1), "look")
        self.assertEqual(self.client.request.call_args.kwargs["params"]["cursor"], "2")

    def test_duplicate_actions_are_not_executed_again(self):
        self.client.request.return_value = {
            "items": [output("1", action(0)), output("2", action(1))], "next_cursor": "2",
        }
        self.assertEqual(self.client.action("terminal", "episode", 1, 1), "look")
        self.assertEqual(self.client.cursor, "2")

    def test_invalid_action_is_reported(self):
        for message in (action(1), action(episode_id="wrong"), action(text=" "),
                        action(step=True), action(step=-1)):
            with self.subTest(message=message):
                self.client.request.return_value = {"items": [output("1", message)], "next_cursor": "1"}
                with self.assertRaises(ProtocolError):
                    self.client.action("terminal", "episode", 0, 1)

    def test_empty_page_keeps_cursor_until_timeout(self):
        self.client.cursor = "existing"
        self.client.request.return_value = {"items": [], "next_cursor": "existing"}
        with self.assertRaises(TimeoutError):
            self.client.action("terminal", "episode", 0, 0.01)
        self.assertEqual(self.client.cursor, "existing")

    def test_failed_post_is_not_retried(self):
        self.client.request = TerminalClient.request.__get__(self.client)
        self.client.session = MagicMock()
        self.client.session.request.return_value.ok = False
        self.client.session.request.return_value.status_code = 503
        self.client.session.request.return_value.text = "saved but not queued"
        with self.assertRaisesRegex(RuntimeError, "503"):
            self.client.send("terminal", {"text": "observation"})
        self.client.session.request.assert_called_once()


class RunnerTest(unittest.TestCase):
    def setUp(self):
        self.env = MagicMock()
        self.env.reset.return_value = (["task"], {"extra.gamefile": ["game.tw-pddl"],
                                                "admissible_commands": [["look"]]})
        self.env.step.return_value = (["done"], [1], [True], {"won": [True], "admissible_commands": [[]]})
        self.client = MagicMock()
        self.client.action.return_value = "look"
        self.trace = []

    def run_episode(self, **kwargs):
        return run_episode(self.env, self.client, "file", {}, kwargs.get("max_steps", 2),
                           1, 1, kwargs.get("include_commands", False), self.trace.append, "episode")

    def test_success_is_based_on_won_and_final_observation_is_sent(self):
        result = self.run_episode()
        self.assertEqual(result["status"], "success")
        self.assertTrue(result["success"])
        self.assertEqual(result["steps"], 1)
        self.env.step.assert_called_once_with(["look"])
        final = self.client.send.call_args.args[1]
        self.assertTrue(final["done"])
        self.assertFalse(final["truncated"])
        self.assertNotIn("admissible_commands", final)
        self.assertEqual([record["direction"] for record in self.trace], ["observation", "action", "observation", "result"])

    def test_step_limit_is_failure_not_success(self):
        self.env.step.return_value = (["nothing"], [0], [False], {"won": [False], "admissible_commands": [["look"]]})
        result = self.run_episode(max_steps=2, include_commands=True)
        self.assertEqual(result["status"], "max_steps")
        self.assertFalse(result["success"])
        self.assertEqual(self.env.step.call_count, 2)
        final = self.client.send.call_args.args[1]
        self.assertTrue(final["done"])
        self.assertTrue(final["truncated"])
        self.assertEqual(final["admissible_commands"], ["look"])

    def test_early_environment_end_is_distinct_from_step_limit(self):
        self.env.step.return_value = (["ended"], [0], [True], {"won": [False]})
        result = self.run_episode(max_steps=5)
        self.assertEqual(result["status"], "environment_done")
        self.assertFalse(result["success"])
        self.assertFalse(self.client.send.call_args.args[1]["truncated"])
        self.env.step.assert_called_once()

    def test_timeout_does_not_step_environment_and_notifies_workflow(self):
        self.client.action.side_effect = TimeoutError("no action")
        result = self.run_episode()
        self.assertEqual(result["status"], "error")
        self.env.step.assert_not_called()
        self.assertEqual(self.client.send.call_args.args[1]["reason"], "runner_error")

    def test_startup_failure_does_not_send_input_to_an_uncreated_terminal(self):
        self.client.start.side_effect = TimeoutError("no terminal")
        result = self.run_episode()
        self.assertEqual(result["status"], "error")
        self.client.send.assert_not_called()
        self.env.step.assert_not_called()

    def test_evaluation_records_error_and_stops_instead_of_masking_it(self):
        self.client.action.side_effect = TimeoutError("no action")
        with tempfile.TemporaryDirectory() as directory:
            args = SimpleNamespace(episodes=2, workflow_file_id="file", inputs={}, split="valid_unseen",
                                   max_steps=2, seed=42, action_timeout=1, startup_timeout=1,
                                   admissible_commands=False, results_dir=directory)
            code = evaluate(self.env, ["a", "b"], self.client, args)
            run_dir = next(Path(directory).iterdir())
            summary = json.loads((run_dir / "summary.json").read_text())
            self.assertEqual(code, 1)
            self.assertEqual(summary["errors"], 1)
            self.assertEqual(summary["completed"], 1)
            self.assertEqual(summary["requested"], 2)
            self.assertEqual(len(list(run_dir.glob("episode-*.jsonl"))), 1)
            self.env.reset.assert_called_once()


if __name__ == "__main__":
    unittest.main()
