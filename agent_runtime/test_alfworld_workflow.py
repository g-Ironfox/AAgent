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
from build_alfworld_workflow import REACT_MODEL_ID, build_workflow


class AlfworldWorkflowTest(unittest.TestCase):
    setUp = support.ProcessWorkflowTest.setUp
    start = support.ProcessWorkflowTest.start
    drain = support.ProcessWorkflowTest.drain
    send = support.ProcessWorkflowTest.send

    def observe(self, process, step, done=False, text="task observation"):
        self.send(process, json.dumps({"type": "observation", "episode_id": "e1", "step": step,
                                       "text": text, "done": done}))
        self.drain()
        saved = main.read_process(process["process_id"]).to_record()
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
        self.assertEqual(main.read_process(root["process_id"]).status, "blocked")
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

    def test_committed_react_example_matches_builder_and_validates(self):
        path = Path(__file__).resolve().parents[1] / "docs/examples/alfworld-react.flow"
        workflow = build_workflow(react=True)
        self.assertEqual(json.loads(path.read_text(encoding="utf-8")), workflow)
        validate_workflow(workflow)
        model_id = "0123456789abcdef01234567"
        configured = build_workflow(model_id, react=True)
        validate_workflow(configured)
        self.assertEqual(next(n for n in workflow["nodes"] if n["type"] == "llm")["arguments"]["model"], REACT_MODEL_ID)
        self.assertEqual(next(n for n in configured["nodes"] if n["type"] == "llm")["arguments"]["model"], model_id)
        self.assertTrue(next(n for n in workflow["nodes"] if n["type"] == "llm")["arguments"]["think"])
        self.assertFalse(any(n["id"] == "parse_decision" for n in workflow["nodes"]))
        self.assertTrue(any(edge["fromId"] == "decide" and edge["fromPortId"] == "reasoning"
                            and edge["toId"] == "assistant" and edge["toPortId"] == "reasoning-in"
                            for edge in workflow["connections"]))

    def test_react_workflow_retains_native_reasoning_but_sends_only_actions(self):
        model_id = "0123456789abcdef01234567"
        decisions = [
            {"reasoning": "Inspect cabinet 1 for the mug.", "action": "open cabinet 1"},
            {"reasoning": "The mug is visible; pick it up.", "action": "take mug 1 from cabinet 1"},
        ]
        observations = ["Your task is to put a mug on countertop 1.", "Cabinet 1 contains mug 1."]
        model = Mock(side_effect=[(decision["action"], decision["reasoning"], []) for decision in decisions])
        with patch.dict("sys.modules", {"llm": SimpleNamespace(chat_with_model=model)}):
            root = self.start(build_workflow(model_id, react=True), inputs={})
            self.drain()
            self.assertEqual(main.read_process(root["process_id"]).status, "blocked")
            model.assert_not_called()
            self.output.assert_not_called()
            for step, (decision, observation) in enumerate(zip(decisions, observations)):
                self.assertEqual(self.observe(root, step, text=observation)["status"], "blocked")
                self.assertEqual(json.loads(self.output.call_args.args[0]), {
                    "type": "action", "episode_id": "e1", "step": step, "text": decision["action"],
                })
            self.assertEqual(self.observe(root, 2, done=True)["status"], "completed")
        self.assertEqual(self.output.call_count, 2)
        self.assertEqual(model.call_count, 2)
        first_history = model.call_args_list[0].args[0]
        history = model.call_args_list[1].args[0]
        self.assertEqual([item["role"] for item in first_history], ["system", "user"])
        self.assertEqual([item["role"] for item in history], ["system", "user", "assistant", "user"])
        self.assertEqual(history[2], {"role": "assistant", "content": decisions[0]["action"],
                                     "reasoning_content": decisions[0]["reasoning"]})
        self.assertEqual([json.loads(history[index]["content"])["text"] for index in (1, 3)], observations)
        self.assertEqual(model.call_args.args[1], model_id)
        self.assertEqual(model.call_args.kwargs, {"tools": [], "think": True})

    def test_react_workflow_exits_on_initial_done_without_calling_model(self):
        model = Mock()
        with patch.dict("sys.modules", {"llm": SimpleNamespace(chat_with_model=model)}):
            root = self.start(build_workflow(react=True), inputs={})
            self.drain()
            self.assertEqual(self.observe(root, 0, done=True)["status"], "completed")
        model.assert_not_called()
        self.output.assert_not_called()

    def test_react_workflow_accepts_plain_commands_with_empty_reasoning(self):
        model = Mock(side_effect=[("look", "", []), ("inventory", "", [])])
        with patch.dict("sys.modules", {"llm": SimpleNamespace(chat_with_model=model)}):
            root = self.start(build_workflow(react=True), inputs={})
            self.drain()
            for step, action in enumerate(("look", "inventory")):
                self.assertEqual(self.observe(root, step)["status"], "blocked")
                self.assertEqual(json.loads(self.output.call_args.args[0])["text"], action)
            self.assertEqual(self.observe(root, 2, done=True)["status"], "completed")
        self.assertEqual(model.call_count, 2)
        self.assertEqual(model.call_args.args[0][2], {
            "role": "assistant", "content": "look", "reasoning_content": "",
        })


if __name__ == "__main__":
    unittest.main()
