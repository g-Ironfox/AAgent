"""Exercise the tool-loop example through the durable workflow scheduler."""
import copy
import json
from pathlib import Path
import runpy
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import main
import test_process_workflows as process_support
from workflow_parser import parse_workflow
from workflow_validator import validate_workflow


EXAMPLE = Path(__file__).parents[1] / "docs" / "examples" / "tool-loop-agent.flow"
TOOL_NAMES = ("workspace.list_files", "workspace.get_file")
TOOL_SCHEMAS = [
    {"type": "function", "function": {
        "name": "workspace.list_files", "description": "List workspace files",
        "parameters": {"type": "object", "properties": {}},
    }},
    {"type": "function", "function": {
        "name": "workspace.get_file", "description": "Read a workspace file",
        "parameters": {"type": "object", "properties": {"file_id": {"type": "string"}},
                        "required": ["file_id"]},
    }},
]


def tool_call(call_id, name, arguments):
    return {"id": call_id, "type": "function", "function": {
        "name": name, "arguments": json.dumps(arguments),
    }}


def example_workflow():
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


class ToolLoopWorkflowTest(unittest.TestCase):
    start = process_support.ProcessWorkflowTest.start
    send = process_support.ProcessWorkflowTest.send

    def setUp(self):
        process_support.ProcessWorkflowTest.setUp(self)
        self.execute = Mock(side_effect=[
            {"items": ["file-a"], "revision": 4},
            {"file_id": "file-a", "content": "file contents"},
        ])
        tools = patch.dict("sys.modules", {"tools.tool": SimpleNamespace(
            registered_tools=copy.deepcopy(TOOL_SCHEMAS),
            tool_handlers={name: object() for name in TOOL_NAMES},
            execute_tool=self.execute,
        )})
        tools.start()
        self.addCleanup(tools.stop)
        self.human_inputs = []
        terminal_reader = patch(
            "terminal_repository.read_terminal_input",
            side_effect=lambda _: list(self.human_inputs),
        )
        terminal_reader.start()
        self.addCleanup(terminal_reader.stop)

    def drain(self):
        for _ in range(1000):
            if main.schedule_once(timeout=0.01) is None:
                return
        self.fail("scheduler failed to quiesce")

    def test_workflow_validates_and_compiles_without_mutation(self):
        workflow = example_workflow()
        before = copy.deepcopy(workflow)
        validate_workflow(workflow)
        graph = parse_workflow(workflow)
        self.assertEqual(workflow, before)
        builder = runpy.run_path(str(EXAMPLE.parents[2] / "scripts" / "build_tool_loop_workflow.py"))
        self.assertEqual(workflow, builder["build_workflow"]())
        nodes = {node["id"]: node for node in graph}
        self.assertEqual(nodes["call_turn"]["arguments"]["function_id"], "tool_loop_turn")
        self.assertEqual(nodes["execute_each"]["arguments"]["function_id"], "run_one_tool")
        self.assertEqual(nodes["llm"]["arguments"]["model"], "REPLACE_WITH_MODEL_ID")
        self.assertEqual(nodes["llm"]["arguments"]["tools_source"], "definitions")

    def test_executes_multiple_calls_then_summarizes_next_turn(self):
        calls = [
            tool_call("list-call", "workspace.list_files", {}),
            tool_call("read-call", "workspace.get_file", {"file_id": "file-a"}),
        ]
        with patch("llm.chat_with_model", side_effect=[
            (None, "Inspecting the workspace", calls),
            ("The file contains the requested information.", "", []),
        ]) as model:
            process = self.start(example_workflow(), inputs={"task": "Find and inspect a file"})
            self.drain()

        final = main.read_process(process["process_id"])
        self.assertEqual(final["status"], "completed", final.get("error"))
        self.assertEqual(model.call_count, 2)
        self.assertEqual(self.execute.call_count, 2)
        self.execute.assert_any_call("invoke_tool", "workspace.list_files", {}, preserve_result=True)
        self.execute.assert_any_call("invoke_tool", "workspace.get_file", {"file_id": "file-a"}, preserve_result=True)
        history = model.call_args.args[0]
        self.assertEqual(history[-3]["tool_calls"], calls)
        self.assertEqual(history[-3]["reasoning_content"], "Inspecting the workspace")
        self.assertEqual([message["role"] for message in history[-2:]], ["tool", "tool"])
        self.assertEqual([message["tool_call_id"] for message in history[-2:]], ["list-call", "read-call"])
        self.assertEqual(json.loads(history[-2]["content"]), {"items": ["file-a"], "revision": 4})
        self.assertEqual(json.loads(history[-1]["content"]), {"file_id": "file-a", "content": "file contents"})
        self.assertEqual(self.output.call_args_list[-1].args[0], "The file contains the requested information.")
        self.assertEqual(sum(event["node_id"] == "turn_gate" for event in final["node_trace"]), 3)

    def test_provider_index_is_removed_before_struct_conversion_and_next_request(self):
        provider_call = {}

        def provider_response(*args, **kwargs):
            payload = kwargs["json"]
            response = Mock(status_code=200)
            if len(payload["messages"]) == 2:
                provider_call.update({
                    "index": 0, "id": "indexed-call", "type": "function", "function": {
                        "name": payload["tools"][0]["function"]["name"], "arguments": "{}",
                    },
                })
                message = {"content": None, "tool_calls": [copy.deepcopy(provider_call)]}
            else:
                self.assertEqual(payload["messages"][-2]["tool_calls"], [{
                    "id": "indexed-call", "type": "function", "function": {
                        "name": provider_call["function"]["name"], "arguments": "{}",
                    },
                }])
                self.assertEqual(payload["messages"][-1]["tool_call_id"], "indexed-call")
                message = {"content": "Workspace inspected.", "tool_calls": []}
            response.json.return_value = {"choices": [{"message": message}]}
            return response

        config = {"model": "test-model", "base_url": "https://example.test/v1", "api_key": "test-key"}
        with patch("llm._model_config", return_value=config), patch(
            "llm.requests.post", side_effect=provider_response,
        ) as request:
            process = self.start(example_workflow(), inputs={"task": "List workspace files"})
            self.drain()

        final = main.read_process(process["process_id"])
        self.assertEqual(final["status"], "completed", final.get("error"))
        self.assertEqual(request.call_count, 2)
        self.execute.assert_called_once_with("invoke_tool", "workspace.list_files", {}, preserve_result=True)
        self.assertEqual(self.output.call_args_list[-1].args[0], "Workspace inspected.")

    def test_tool_error_is_recorded_and_model_can_continue(self):
        self.execute.side_effect = RuntimeError("temporary tool failure")
        with patch("llm.chat_with_model", side_effect=[
            (None, "Reading the file", [tool_call("read-call", "workspace.get_file", {"file_id": "missing"})]),
            ("The read failed, so I cannot confirm the contents.", "", []),
        ]) as model:
            process = self.start(example_workflow(), inputs={"task": "Read a file"})
            self.drain()

        final = main.read_process(process["process_id"])
        self.assertEqual(final["status"], "completed", final.get("error"))
        self.assertEqual(model.call_count, 2)
        self.execute.assert_called_once()
        observation = json.loads(model.call_args.args[0][-1]["content"])
        self.assertEqual(model.call_args.args[0][-1]["tool_call_id"], "read-call")
        self.assertEqual(observation["error"]["message"], "temporary tool failure")

    def test_ask_human_blocks_resumes_and_skips_stale_calls_from_same_batch(self):
        calls = [
            tool_call("human-call", "ask_human", {"question": "Which file should I inspect?"}),
            tool_call("stale-call", "workspace.get_file", {"file_id": "old-plan"}),
        ]
        with patch("llm.chat_with_model", side_effect=[
            (None, "I need one detail", calls),
            ("I will inspect the file you selected.", "", []),
        ]) as model:
            process = self.start(example_workflow(), inputs={"task": "Inspect a file"})
            self.drain()
            waiting = main.read_process(process["process_id"])
            self.assertEqual(waiting["status"], "blocked", waiting.get("error"))
            self.assertEqual(waiting["active_function_id"], "run_one_tool")
            self.assertEqual(model.call_count, 1)
            self.assertIn("Which file should I inspect?", self.output.call_args_list[-1].args[0])

            self.human_inputs.append("src/settings.py")
            self.send(waiting, text="src/settings.py")
            self.drain()

        final = main.read_process(process["process_id"])
        self.assertEqual(final["status"], "completed", final.get("error"))
        self.assertEqual(model.call_count, 2)
        self.execute.assert_not_called()
        history = model.call_args.args[0]
        self.assertEqual([item["tool_call_id"] for item in history[-2:]], ["human-call", "stale-call"])
        self.assertEqual(json.loads(history[-2]["content"]), {"replies": ["src/settings.py"]})
        self.assertIn("Skipped because ask_human changed the plan", history[-1]["content"])

    def test_repeated_questions_use_new_slices_and_allow_tools_in_next_batch(self):
        self.human_inputs.extend(["old terminal input", "another old message"])
        with patch("llm.chat_with_model", side_effect=[
            (None, "", [tool_call("question-1", "ask_human", {"question": "Which file?"})]),
            (None, "", [tool_call("question-2", "ask_human", {"question": "Which details?"})]),
            (None, "", [tool_call("fresh-read", "workspace.get_file", {"file_id": "file-a"})]),
            ("Read the file using your answers.", "", []),
        ]) as model:
            process = self.start(example_workflow(), inputs={"task": "Inspect a file"})
            self.drain()
            waiting = main.read_process(process["process_id"])
            self.assertEqual(waiting["status"], "blocked", waiting.get("error"))
            self.assertEqual(model.call_count, 1)
            self.assertEqual(len(waiting["function_stack"]), 2)
            self.human_inputs.extend(["file-a", "Please include its configuration"])
            self.send(waiting, text="file-a")
            self.drain()

            waiting = main.read_process(process["process_id"])
            self.assertEqual(waiting["status"], "blocked", waiting.get("error"))
            self.assertEqual(model.call_count, 2)
            first_observation = model.call_args.args[0][-1]
            self.assertEqual(first_observation["tool_call_id"], "question-1")
            self.assertEqual(json.loads(first_observation["content"]), {
                "replies": ["file-a", "Please include its configuration"],
            })
            self.execute.assert_not_called()
            self.human_inputs.append("Only configuration")
            self.send(waiting, text="Only configuration")
            self.drain()

        final = main.read_process(process["process_id"])
        self.assertEqual(final["status"], "completed", final.get("error"))
        self.assertEqual(model.call_count, 4)
        history = model.call_args_list[2].args[0]
        self.assertEqual(history[-1]["tool_call_id"], "question-2")
        self.assertEqual(json.loads(history[-1]["content"]), {"replies": ["Only configuration"]})
        self.execute.assert_called_once_with(
            "invoke_tool", "workspace.get_file", {"file_id": "file-a"}, preserve_result=True,
        )
        definitions = model.call_args.kwargs["tools"]
        self.assertEqual([item["function"]["name"] for item in definitions], [*TOOL_NAMES, "ask_human"])
        ask_parameters = definitions[-1]["function"]["parameters"]
        self.assertEqual(ask_parameters["required"], ["question"])


if __name__ == "__main__":
    unittest.main()
