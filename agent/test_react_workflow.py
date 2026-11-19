"""Validate and execute the example through the durable process scheduler."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import main
import test_process_workflows as support
from workflow_parser import parse_workflow
from workflow_validator import WorkflowValidationError, validate_workflow


EXAMPLE = Path(__file__).parents[1] / "docs" / "examples" / "react-human-in-loop.flow"


def example_workflow():
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


class ReactHumanInLoopWorkflowTest(unittest.TestCase):
    def test_example_validates_and_compiles_without_modifying_document(self):
        workflow = example_workflow()
        before = copy.deepcopy(workflow)
        validate_workflow(workflow)
        graph = parse_workflow(workflow)
        self.assertEqual(workflow, before)
        nodes = {node["id"]: node for node in graph}
        self.assertEqual(nodes["call_turn"]["arguments"]["function_id"], "react_turn")
        self.assertEqual(nodes["turn_gate"]["successors"]["item"], graph.index(nodes["call_turn"]))
        self.assertEqual(nodes["call_turn"]["successors"]["next"], graph.index(nodes["turn_gate"]))
        self.assertEqual(nodes["done_gate"]["successors"]["branch-DONE"], graph.index(nodes["turn_done"]))
        self.assertEqual(nodes["done_gate"]["successors"]["branch$others"], graph.index(nodes["observation_message"]))

    def test_direct_router_in_loop_remains_forbidden(self):
        workflow = example_workflow()
        call = next(n for n in workflow["nodes"] if n["id"] == "call_turn")
        call.update(type="router", arguments={"branches": []})
        for edge in workflow["connections"]:
            if edge["fromId"] == "call_turn":
                edge["fromPortId"] = "branch$others"
        workflow["connections"] = [e for e in workflow["connections"]
                                   if e["toId"] != "call_turn" or e["type"] == "control"]
        with self.assertRaisesRegex(WorkflowValidationError, "branching control flow"):
            validate_workflow(workflow)


class ReactHumanInLoopProcessTest(unittest.TestCase):
    start = support.ProcessWorkflowTest.start
    drain = support.ProcessWorkflowTest.drain
    send = support.ProcessWorkflowTest.send

    def setUp(self):
        support.ProcessWorkflowTest.setUp(self)
        tools = patch.dict("sys.modules", {"tools.tool": SimpleNamespace(registered_tools=[])})
        tools.start()
        self.addCleanup(tools.stop)
        self.human_inputs = []
        reader = patch("terminal_repository.read_terminal_input", side_effect=lambda _: list(self.human_inputs))
        reader.start()
        self.addCleanup(reader.stop)
        model = patch("llm.chat_with_model", side_effect=[
            ("Proposal 1", "", []), ("Proposal 2", "", []), ("Proposal 3", "", []),
        ])
        self.model = model.start()
        self.addCleanup(model.stop)

    def assert_waiting(self, process_id, expected_calls):
        waiting = main.read_process(process_id)
        self.assertEqual(waiting["status"], "blocked", waiting.get("error"))
        self.assertEqual(waiting["active_function_id"], "react_turn")
        self.assertEqual(len(waiting["function_stack"]), 1)
        self.assertEqual(waiting["wait_for"]["kind"], "terminal_message")
        self.assertEqual(self.model.call_count, expected_calls)
        return waiting

    def reply(self, waiting, text):
        self.human_inputs.append(text)
        self.send(waiting, text=text)
        self.drain()

    def test_multiple_turns_rejection_and_done_through_scheduler(self):
        process = self.start(example_workflow(), inputs={"task": "Investigate the failing job"})
        self.drain()
        waiting = self.assert_waiting(process["process_id"], 1)
        self.assertEqual([c.args[0] for c in self.output.call_args_list], ["Proposal 1"])
        # A repeated scheduler drain without an input must not run the model again.
        self.drain()
        self.assert_waiting(process["process_id"], 1)

        self.reply(waiting, "Rejected: inspect the logs before retrying")
        waiting = self.assert_waiting(process["process_id"], 2)
        second_history = self.model.call_args_list[1].args[0]
        self.assertEqual([(m["role"], m["content"]) for m in second_history[1:]], [
            ("user", "Investigate the failing job"),
            ("assistant", "Proposal 1"),
            ("user", "Rejected: inspect the logs before retrying"),
        ])
        self.reply(waiting, "Observation: logs show a missing configuration file")
        waiting = self.assert_waiting(process["process_id"], 3)
        third_history = self.model.call_args_list[2].args[0]
        self.assertEqual(third_history[-2:], [
            {"role": "assistant", "content": "Proposal 2"},
            {"role": "user", "content": "Observation: logs show a missing configuration file"},
        ])
        self.reply(waiting, "DONE")
        final = main.read_process(process["process_id"])
        self.assertEqual(final["status"], "completed", final.get("error"))
        self.assertEqual(final["function_stack"], [])
        self.assertEqual(final["result"], {})
        self.assertEqual(self.model.call_count, 3)
        self.assertEqual([c.args[0] for c in self.output.call_args_list], ["Proposal 1", "Proposal 2", "Proposal 3"])
        self.assertEqual(sum(t["node_id"] == "create_history" for t in final["node_trace"]), 1)
        self.assertEqual(sum(t["node_id"] == "turn_continue" for t in final["node_trace"]), 2)
        self.assertEqual(sum(t["node_id"] == "turn_done" for t in final["node_trace"]), 1)

    def test_done_on_first_turn_does_not_request_another_completion(self):
        process = self.start(example_workflow(), inputs={"task": "Give one suggestion"})
        self.drain()
        waiting = self.assert_waiting(process["process_id"], 1)
        self.reply(waiting, "DONE")
        final = main.read_process(process["process_id"])
        self.assertEqual(final["status"], "completed", final.get("error"))
        self.assertEqual(self.model.call_count, 1)
        self.assertFalse(any(t["node_id"] == "append_turn_token" for t in final["node_trace"]))


if __name__ == "__main__":
    unittest.main()
