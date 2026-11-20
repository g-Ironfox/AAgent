"""Exercise the ALFWorld examples through the real durable scheduler."""

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from types import SimpleNamespace

import main
import test_process_workflows as support
from workflow_validator import validate_workflow

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from build_alfworld_workflow import build_workflow


class AlfworldWorkflowTest(unittest.TestCase):
    setUp = support.ProcessWorkflowTest.setUp
    start = support.ProcessWorkflowTest.start
    drain = support.ProcessWorkflowTest.drain
    send = support.ProcessWorkflowTest.send

    def observe(self, process, step, done=False):
        self.send(process, json.dumps({"type": "observation", "episode_id": "e1", "step": step,
                                       "text": "task observation", "done": done}))
        self.drain()
        saved = main.read_process(process["process_id"])
        self.assertNotEqual(saved["status"], "failed", saved.get("error"))
        return saved

    def test_committed_smoke_example_matches_builder_and_validates(self):
        path = Path(__file__).resolve().parents[1] / "docs/examples/alfworld-look.flow"
        self.assertEqual(json.loads(path.read_text(encoding="utf-8")), build_workflow())
        validate_workflow(build_workflow())
        validate_workflow(build_workflow("0123456789abcdef01234567"))

    def test_smoke_workflow_waits_emits_matching_actions_then_exits(self):
        root = self.start(build_workflow(), inputs={})
        self.drain()
        self.assertEqual(main.read_process(root["process_id"])["status"], "blocked")
        self.output.assert_not_called()
        for step in range(2):
            self.assertEqual(self.observe(root, step)["status"], "blocked")
            self.assertEqual(json.loads(self.output.call_args.args[0]), {
                "type": "action", "episode_id": "e1", "step": step, "text": "look",
            })
        self.assertEqual(self.observe(root, 2, done=True)["status"], "completed")
        self.assertEqual(self.output.call_count, 2)

    def test_model_workflow_retains_history_and_does_not_call_model_when_done(self):
        model = Mock(side_effect=[("look", "", []), ("open cabinet 1", "", [])])
        with patch.dict("sys.modules", {"llm": SimpleNamespace(chat_with_model=model)}):
            root = self.start(build_workflow("0123456789abcdef01234567"), inputs={})
            self.drain()
            self.observe(root, 0)
            self.observe(root, 1)
            self.assertEqual(self.observe(root, 2, done=True)["status"], "completed")
        self.assertEqual(model.call_count, 2)
        history = model.call_args.args[0]
        self.assertEqual([item["role"] for item in history], ["system", "user", "assistant", "user"])
        self.assertEqual(history[2]["content"], "look")
        self.assertEqual(json.loads(self.output.call_args.args[0])["text"], "open cabinet 1")


if __name__ == "__main__":
    unittest.main()
