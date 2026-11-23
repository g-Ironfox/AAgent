"""Tool JSON construction, dynamic LLM definitions and wire compatibility."""
import copy
import itertools
import json
import unittest
import sys
import types
from unittest.mock import Mock, patch

from test_support import run_scheduled_workflow
from workflow_contract import data_ports_for_node
from workflow_nodes import propagate_workflow_output, workflow_construct_tool, workflow_llm
from workflow_parser import parse_workflow
from workflow_tools import build_tool, parse_tool_contents
from workflow_validator import WorkflowValidationError, _validate_workflow_schema, validate_workflow

SCHEMA = {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}
CALL = {"id": "call_1", "type": "function", "function": {"name": "normalize", "arguments": '{"text":"hello"}'}}


def edge(source, source_port, target, target_port, kind="control"):
    return {"fromId": source, "fromPortId": source_port, "toId": target, "toPortId": target_port, "type": kind}


def fixture():
    return {
        "schema_version": "2.0", "metadata": {"structs": [], "tools": []},
        "input_ports": [{"name": "messages", "type": "list-content"}],
        "output_ports": [{"name": "calls", "type": "list-content"}],
        "nodes": [
            {"id": "input", "type": "input", "workflowPorts": [{"id": "workflow:messages", "name": "messages", "type": "list-content"}]},
            {"id": "a", "type": "construct_tool", "arguments": {"tool_name": "normalize", "description": "Normalize", "schema": copy.deepcopy(SCHEMA)}},
            {"id": "b", "type": "construct_tool", "arguments": {"tool_name": "search", "description": "Search", "schema": {"type": "object", "properties": {}}}},
            {"id": "list", "type": "construct_list", "arguments": {"item_type": "content", "initial_value_count": 2}, "dataInputPorts": ["content-in-0", "content-in-1"]},
            {"id": "llm", "type": "llm", "arguments": {"model": "model-id", "tool_calls": True, "tools_source": "definitions"}},
            {"id": "output", "type": "output", "workflowPorts": [{"id": "workflow:calls", "name": "calls", "type": "list-content"}]},
        ],
        "connections": [
            edge("input", "control-out", "a", "control-in"), edge("a", "control-out", "b", "control-in"),
            edge("b", "control-out", "list", "control-in"), edge("list", "control-out", "llm", "control-in"),
            edge("llm", "control-out", "output", "control-in"),
            edge("a", "tool-out", "list", "content-in-0", "content"), edge("b", "tool-out", "list", "content-in-1", "content"),
            edge("list", "list-out", "llm", "tools-in", "list-content"),
            edge("input", "workflow:messages", "llm", "messages-in", "list-content"),
            edge("llm", "tool_calls", "output", "workflow:calls", "list-content"),
        ],
    }


class ToolTestCase(unittest.TestCase):
    def setUp(self):
        modules = patch.dict(sys.modules, {"llm": types.SimpleNamespace(chat_with_model=Mock())})
        modules.start()
        self.addCleanup(modules.stop)


class ToolConstructionTest(ToolTestCase):
    def test_two_tools_reach_llm_without_metadata_and_calls_keep_ids_and_arguments(self):
        document = fixture()
        _validate_workflow_schema(document)
        validate_workflow(document)
        graph = parse_workflow(document)
        messages = ['{"role":"user","content":"hello"}']
        propagate_workflow_output(graph, graph[0], "workflow:messages", messages)
        with patch("llm.chat_with_model", return_value=("", "", [CALL])) as chat, patch("tool_server_client.get_remote_tool_schemas") as remote:
            result = run_scheduled_workflow(graph, 0)
        self.assertEqual(json.loads(result["calls"][0]), CALL)
        self.assertEqual(chat.call_args.args, ([{"role": "user", "content": "hello"}], "model-id"))
        self.assertEqual([t["function"]["name"] for t in chat.call_args.kwargs["tools"]], ["normalize", "search"])
        remote.assert_not_called()

    def test_all_sixteen_fixed_and_port_combinations_have_same_output(self):
        fields = ["tool_name", "description", "schema", "required"]
        ports = ["name-in", "description-in", "schema-in", "required-in"]
        values = ["normalize", "Normalize text", SCHEMA, ["text"]]
        for mask in itertools.product([False, True], repeat=4):
            with self.subTest(mask=mask):
                args, inputs = {}, {}
                for field, port, value, dynamic in zip(fields, ports, values, mask):
                    args[field + "_source"] = "port" if dynamic else "fixed"
                    if dynamic:
                        inputs[port] = [0, "value", json.dumps(value) if field == "schema" else value]
                    else:
                        args[field] = copy.deepcopy(value)
                graph = [{"id": "tool", "type": "construct_tool", "arguments": args, "data_inputs": inputs,
                          "data_outputs": {"tool-out": [[1, "result"]]}, "successors": {"next": 1}},
                         {"data_inputs": {"result": [0, "tool-out", None]}}]
                self.assertEqual(data_ports_for_node(graph[0], [], [])[0], set(inputs))
                self.assertEqual(workflow_construct_tool(0, graph), 1)
                self.assertEqual(json.loads(graph[1]["data_inputs"]["result"][2]), build_tool(*values))

    def test_required_inherits_overrides_and_clears_without_mutating_schema(self):
        original = copy.deepcopy(SCHEMA)
        self.assertEqual(build_tool("f", "", SCHEMA)["function"]["parameters"]["required"], ["text"])
        self.assertEqual(build_tool("f", "", SCHEMA, [])["function"]["parameters"]["required"], [])
        self.assertEqual(build_tool("f", "", json.dumps(SCHEMA))["function"]["parameters"], SCHEMA)
        self.assertEqual(SCHEMA, original)

    def test_invalid_fixed_definitions_fail_on_validation(self):
        cases = [{"tool_name": " "}, {"schema": "{"}, {"schema": {"type": "array"}},
                 {"schema": {"type": "object", "properties": {"x": {"type": "invalid"}}}},
                 {"required": ["missing"]}, {"required": ["text", "text"]}, {"required": None},
                 {"description": 1}, {"schema_source": "bad"}]
        for change in cases:
            with self.subTest(change=change):
                document = fixture()
                document["nodes"][1]["arguments"].update(change)
                with self.assertRaises(WorkflowValidationError):
                    validate_workflow(document)

    def test_dynamic_ports_and_llm_definitions_require_connections_and_correct_types(self):
        document = fixture()
        document["nodes"][1]["arguments"]["required_source"] = "port"
        with self.assertRaisesRegex(WorkflowValidationError, "required-in"):
            validate_workflow(document)
        document = fixture()
        document["connections"] = [e for e in document["connections"] if e["toPortId"] != "tools-in"]
        with self.assertRaisesRegex(WorkflowValidationError, "tools-in"):
            validate_workflow(document)
        document = fixture()
        document["connections"][5]["type"] = "list-content"
        with self.assertRaises(WorkflowValidationError):
            validate_workflow(document)

    def test_missing_dynamic_value_fails_at_runtime(self):
        graph = [{"id": "tool", "type": "construct_tool", "arguments": {"tool_name_source": "port"}, "data_inputs": {}, "successors": {"next": 1}}]
        with self.assertRaisesRegex(ValueError, "name-in input is missing"):
            workflow_construct_tool(0, graph)

    def test_invalid_dynamic_schema_has_field_specific_error(self):
        graph = [{"id": "tool", "type": "construct_tool", "arguments": {"tool_name": "x", "schema_source": "port"},
                  "data_inputs": {"schema-in": [0, "value", "{"]}}]
        with self.assertRaisesRegex(ValueError, "schema-in invalid JSON"):
            workflow_construct_tool(0, graph)


class ToolDefinitionInputTest(ToolTestCase):
    def graph(self, contents):
        return [{"id": "llm", "type": "llm", "arguments": {"model": "model-id", "tool_calls": True, "tools_source": "definitions"},
                 "data_inputs": {"messages-in": [0, "messages", ['{"role":"user","content":"hello"}']], "tools-in": [0, "list-out", contents]},
                 "data_outputs": {"tool_calls": [[1, "calls"]]}, "successors": {"next": 1}},
                {"data_inputs": {"calls": [0, "tool_calls", None]}}]

    def test_empty_list_disables_tools_and_no_calls_outputs_empty_list(self):
        graph = self.graph([])
        with patch("llm.chat_with_model", return_value=("answer", "", [])) as chat:
            workflow_llm(0, graph)
        self.assertEqual(chat.call_args.kwargs["tools"], [])
        self.assertEqual(graph[1]["data_inputs"]["calls"][2], [])

    def test_missing_input_fails_before_model_request(self):
        with patch("llm.chat_with_model") as chat:
            with self.assertRaisesRegex(ValueError, "tools-in input is missing"):
                workflow_llm(0, self.graph(None))
        chat.assert_not_called()

    def test_malformed_and_duplicate_items_fail_with_item_index(self):
        valid = json.dumps(build_tool("f", "", SCHEMA))
        invalid = ["{", "null", "[]", "1", '"f"', "{}", {"type": "function"},
                   json.dumps({"type": "function", "function": {"name": "x", "parameters": {"type": "object", "required": ["missing"]}}}), valid]
        for item in invalid:
            with self.subTest(item=item), patch("llm.chat_with_model") as chat:
                with self.assertRaisesRegex(ValueError, "item 2"):
                    workflow_llm(0, self.graph([valid, item]))
                chat.assert_not_called()
        with self.assertRaisesRegex(ValueError, "list-content"):
            parse_tool_contents(valid)

    def test_turning_off_tool_calls_does_not_require_definition_input(self):
        graph = self.graph(None)
        graph[0]["arguments"]["tool_calls"] = False
        with patch("llm.chat_with_model", return_value=("answer", "", [])) as chat:
            workflow_llm(0, graph)
        self.assertEqual(chat.call_args.kwargs["tools"], [])


if __name__ == "__main__":
    unittest.main()
