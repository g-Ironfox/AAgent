"""Validate and execute the example through the durable process scheduler."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import main
import test_process_workflows as support
from workflow_parser import parse_workflow
from workflow_validator import WorkflowValidationError, validate_workflow


TOOL_SCHEMAS = [
    {"type": "function", "function": {"name": name, "description": name,
     "parameters": {"type": "object", "properties": {"file_id": {"type": "string"}}}}}
    for name in ("workspace.list_files", "workspace.get_file")
]


def tool_call(id="call_1", name="workspace.list_files", arguments="{}"):
    return {"id": id, "type": "function", "function": {"name": name, "arguments": arguments}}


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
        self.assertEqual(nodes["review_each_tool"]["arguments"]["function_id"], "review_tool")
        self.assertTrue(nodes["llm"]["arguments"]["tool_calls"])
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
    send = support.ProcessWorkflowTest.send

    def setUp(self):
        support.ProcessWorkflowTest.setUp(self)
        self.execute = Mock(return_value={"items": [], "revision": 1})
        tools = patch.dict("sys.modules", {"tools.tool": SimpleNamespace(
            registered_tools=copy.deepcopy(TOOL_SCHEMAS),
            tool_handlers={name: object() for name in ("workspace.list_files", "workspace.get_file")},
            execute_tool=self.execute,
        )})
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

    def drain(self):
        # Nested functions perform several real scheduler steps per tool result.
        for _ in range(1000):
            if main.schedule_once(timeout=1) is None:
                return
        self.fail("scheduler failed to quiesce")

    def assert_waiting(self, process_id, expected_calls, tool=False):
        waiting = main.read_process(process_id)
        self.assertEqual(waiting["status"], "blocked", waiting.get("error"))
        self.assertEqual(waiting["active_function_id"], "review_tool" if tool else "react_turn")
        self.assertEqual(len(waiting["function_stack"]), 2 if tool else 1)
        self.assertEqual(waiting["wait_for"]["kind"], "terminal_message")
        self.assertEqual(self.model.call_count, expected_calls)
        return waiting

    def reply(self, waiting, text):
        self.human_inputs.append(text)
        self.send(waiting, text=text)
        self.drain()

    def test_multiple_turns_rejection_and_done_through_scheduler(self):
        self.model.side_effect = [
            ("Proposal 1", "Consider the logs first", []),
            ("Proposal 2", "", []), ("Proposal 3", "", []),
        ]
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
        self.assertEqual(second_history[-2]["reasoning_content"], "Consider the logs first")
        self.assertNotIn("tool_calls", second_history[-2])
        self.reply(waiting, "Observation: logs show a missing configuration file")
        waiting = self.assert_waiting(process["process_id"], 3)
        third_history = self.model.call_args_list[2].args[0]
        self.assertEqual(third_history[-2:], [
            {"role": "assistant", "content": "Proposal 2", "reasoning_content": ""},
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
        self.assertFalse(any(t["node_id"] in {"queue_after_text", "queue_after_tools"}
                             for t in final["node_trace"]))

    def test_native_tool_call_requires_approval_and_preserves_messages(self):
        call = tool_call(name="workspace.get_file")
        # Include quotes, a backslash and Unicode in real JSON arguments.
        arguments = {"file_id": 'file-"quoted"-\\-\u4e2d\u6587'}
        call["function"]["arguments"] = json.dumps(arguments)
        self.model.side_effect = [(None, "Need the file contents", [call]), ("File inspected", "", [])]
        process = self.start(example_workflow(), inputs={"task": "Inspect the file"})
        self.drain()
        waiting = self.assert_waiting(process["process_id"], 1, tool=True)
        self.execute.assert_not_called()
        prompt = self.output.call_args_list[-1].args[0]
        self.assertIn("APPROVE", prompt)
        self.assertIn(json.dumps(call, ensure_ascii=False), prompt)
        self.assertEqual(self.model.call_args.kwargs["tools"], TOOL_SCHEMAS)
        self.drain()
        self.execute.assert_not_called()

        self.reply(waiting, "APPROVE")
        waiting = self.assert_waiting(process["process_id"], 2)
        self.execute.assert_called_once_with("execute_tool", "workspace.get_file", arguments, preserve_result=True)
        messages = self.model.call_args.args[0]
        self.assertEqual(messages[-2], {"role": "assistant", "content": "", "reasoning_content": "Need the file contents", "tool_calls": [call]})
        self.assertEqual(messages[-1]["role"], "tool")
        self.assertEqual(messages[-1]["tool_call_id"], "call_1")
        self.assertEqual(json.loads(messages[-1]["content"]), {"items": [], "revision": 1})
        self.reply(waiting, "DONE")
        self.assertEqual(main.read_process(process["process_id"])["status"], "completed")
        self.execute.assert_called_once()

    def test_rejection_is_an_observation_and_never_executes(self):
        self.model.side_effect = [("Proposed lookup", "", [tool_call()]), ("Alternative", "", [])]
        process = self.start(example_workflow(), inputs={"task": "Inspect files"})
        self.drain()
        waiting = self.assert_waiting(process["process_id"], 1, tool=True)
        self.reply(waiting, "Reject: inspect another file first")
        waiting = self.assert_waiting(process["process_id"], 2)
        self.execute.assert_not_called()
        result = self.model.call_args.args[0][-1]
        self.assertEqual(result["tool_call_id"], "call_1")
        self.assertIn("Rejected by human", result["content"])
        self.assertIn("inspect another file first", result["content"])
        self.reply(waiting, "DONE")

    def test_approval_is_exact_and_cannot_execute_from_normal_feedback(self):
        self.model.side_effect = [("Lookup", "", [tool_call()]), ("Alternative", "", [])]
        process = self.start(example_workflow(), inputs={"task": "Inspect files"})
        self.drain()
        waiting = self.assert_waiting(process["process_id"], 1, tool=True)
        self.reply(waiting, "approve")
        self.assert_waiting(process["process_id"], 2)
        self.execute.assert_not_called()

    def test_tool_failure_returns_error_observation_without_failing_process(self):
        self.execute.side_effect = RuntimeError("provider unavailable")
        self.model.side_effect = [("Lookup", "", [tool_call()]), ("Retry later", "", [])]
        process = self.start(example_workflow(), inputs={"task": "Inspect files"})
        self.drain()
        waiting = self.assert_waiting(process["process_id"], 1, tool=True)
        self.reply(waiting, "APPROVE")
        waiting = self.assert_waiting(process["process_id"], 2)
        observation = self.model.call_args.args[0][-1]
        self.assertEqual(observation["tool_call_id"], "call_1")
        self.assertEqual(json.loads(observation["content"])["error"]["message"], "provider unavailable")
        self.reply(waiting, "DONE")
        self.assertEqual(main.read_process(process["process_id"])["status"], "completed")

    def test_invalid_arguments_are_reported_without_executing_tool(self):
        self.model.side_effect = [("Lookup", "", [tool_call(arguments="[]")]), ("Fix arguments", "", [])]
        process = self.start(example_workflow(), inputs={"task": "Inspect files"})
        self.drain()
        waiting = self.assert_waiting(process["process_id"], 1, tool=True)
        self.reply(waiting, "APPROVE")
        self.assert_waiting(process["process_id"], 2)
        self.execute.assert_not_called()
        error = json.loads(self.model.call_args.args[0][-1]["content"])["error"]
        self.assertIn("JSON object", error["message"])

    def test_batch_records_all_results_in_order_before_next_completion(self):
        calls = [tool_call("call_first"), tool_call("call_second", "workspace.get_file", '{"file_id":"demo"}')]
        self.model.side_effect = [(None, "Inspect two sources", calls), ("Review complete", "", [])]
        process = self.start(example_workflow(), inputs={"task": "Inspect files"})
        self.drain()
        waiting = self.assert_waiting(process["process_id"], 1, tool=True)
        self.execute.assert_not_called()

        self.reply(waiting, "APPROVE")
        waiting = self.assert_waiting(process["process_id"], 1, tool=True)
        self.execute.assert_called_once_with("execute_tool", "workspace.list_files", {}, preserve_result=True)
        self.assertIn('"call_second"', self.output.call_args_list[-1].args[0])

        self.reply(waiting, "Skip the second source")
        waiting = self.assert_waiting(process["process_id"], 2)
        messages = self.model.call_args.args[0]
        self.assertEqual(messages[-3]["tool_calls"], calls)
        self.assertEqual([item["role"] for item in messages[-3:]], ["assistant", "tool", "tool"])
        self.assertEqual([item["tool_call_id"] for item in messages[-2:]], ["call_first", "call_second"])
        self.assertEqual(json.loads(messages[-2]["content"]), {"items": [], "revision": 1})
        self.assertIn("Skip the second source", messages[-1]["content"])
        self.execute.assert_called_once()
        self.reply(waiting, "DONE")
        self.assertEqual(main.read_process(process["process_id"])["status"], "completed")

    def test_done_cancels_remaining_calls_in_batch(self):
        self.model.side_effect = [(None, "", [tool_call("call_1"), tool_call("call_2"), tool_call("call_3")])]
        process = self.start(example_workflow(), inputs={"task": "Inspect files"})
        self.drain()
        waiting = self.assert_waiting(process["process_id"], 1, tool=True)
        self.reply(waiting, "APPROVE")
        waiting = self.assert_waiting(process["process_id"], 1, tool=True)
        self.assertIn('"call_2"', self.output.call_args_list[-1].args[0])
        self.reply(waiting, "DONE")
        final = main.read_process(process["process_id"])
        self.assertEqual(final["status"], "completed", final.get("error"))
        self.execute.assert_called_once()
        self.assertEqual(self.model.call_count, 1)
        self.assertEqual(sum("APPROVE" in c.args[0] for c in self.output.call_args_list), 2)
        self.assertEqual(sum(t["node_id"] == "review_skip_return" for t in final["node_trace"]), 1)
        self.assertEqual(sum(t["node_id"] == "turn_tools_done" for t in final["node_trace"]), 1)


if __name__ == "__main__":
    unittest.main()
