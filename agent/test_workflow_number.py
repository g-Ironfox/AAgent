"""Number ports retain numeric values across workflow boundaries and storage."""
import json
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from workflow_contract import is_number_value
from workflow_context_repository import WorkflowContextError, _serialize as serialize_context
from test_support import run_scheduled_workflow
from workflow_nodes import (
    _deserialize_json_value, _tool_arguments, propagate_workflow_output,
    workflow_local_tool, workflow_remote_sync_tool,
)
from workflow_parser import parse_workflow
from workflow_session_repository import WorkflowSessionError, _serialize as serialize_session
from workflow_structs import StructValidationError, validate_struct_definitions, validate_value
from workflow_validator import WorkflowValidationError, validate_workflow


INVALID_NUMBERS = [True, False, None, "12", [], {}, float("nan"), float("inf"), -float("inf")]


def workflow_fixture(deserialize=False):
    input_type = "content" if deserialize else "number"
    workflow = {
        "schema_version": "2.0", "name": "number_roundtrip",
        "input_ports": [{"name": "value", "type": input_type}],
        "output_ports": [{"name": "result", "type": "number"}],
        "nodes": [
            {"id": "input", "type": "input", "workflowPorts": [
                {"id": "workflow:value", "name": "value", "type": input_type}]},
            {"id": "output", "type": "output", "workflowPorts": [
                {"id": "workflow:result", "name": "result", "type": "number"}]},
        ],
        "connections": [],
    }
    if deserialize:
        workflow["nodes"].insert(1, {"id": "parse", "type": "deserialize_json",
            "arguments": {"outputs": [{"key": "value", "type": "number"}]}})
        workflow["connections"].extend([
            {"id": "parse-control", "fromId": "input", "fromPortId": "control-out",
             "toId": "parse", "toPortId": "control-in", "type": "control"},
            {"id": "parse-data", "fromId": "input", "fromPortId": "workflow:value",
             "toId": "parse", "toPortId": "content-in", "type": "content"},
        ])
    source, port = ("parse", "value") if deserialize else ("input", "workflow:value")
    workflow["connections"].extend([
        {"id": "control", "fromId": source, "fromPortId": "control-out",
         "toId": "output", "toPortId": "control-in", "type": "control"},
        {"id": "data", "fromId": source, "fromPortId": port,
         "toId": "output", "toPortId": "workflow:result", "type": "number"},
    ])
    return workflow


class WorkflowNumberTest(unittest.TestCase):
    def test_finite_numbers_are_valid_without_coercion(self):
        for value in (0, -12, 7, 0.0, -1.25, 1e100, 10 ** 400):
            with self.subTest(value=value):
                self.assertTrue(is_number_value(value))
                self.assertIs(validate_value("number", value, {}), value)
                self.assertIs(_deserialize_json_value(value, "number"), value)
                self.assertEqual(json.loads(serialize_context("number", value)), value)
                self.assertEqual(json.loads(serialize_session("number", value)), value)

    def test_invalid_numbers_are_rejected_at_typed_value_boundaries(self):
        for value in INVALID_NUMBERS:
            with self.subTest(value=value):
                self.assertFalse(is_number_value(value))
                for validate, error in (
                    (lambda: validate_value("number", value, {}), StructValidationError),
                    (lambda: _deserialize_json_value(value, "number"), ValueError),
                    (lambda: serialize_context("number", value), WorkflowContextError),
                    (lambda: serialize_session("number", value), WorkflowSessionError),
                ):
                    with self.assertRaises(error):
                        validate()

    def test_number_struct_fields_validate_recursively(self):
        definitions = validate_struct_definitions([{
            "id": "metric", "name": "Metric", "color": "#147d78",
            "fields": [{"name": "value", "type": "number", "required": True}],
        }])
        self.assertEqual(validate_value("list-struct:metric", [{"value": 0}, {"value": 1.25}], definitions),
                         [{"value": 0}, {"value": 1.25}])
        for value in INVALID_NUMBERS:
            with self.subTest(value=value), self.assertRaisesRegex(StructValidationError, r"\$\[0\]\.value"):
                validate_value("list-struct:metric", [{"value": value}], definitions)

    def test_number_edges_and_json_extraction_execute(self):
        for deserialize in (False, True):
            workflow = workflow_fixture(deserialize)
            validate_workflow(workflow)
            for value in (0, -12, 0.0, 3.5):
                with self.subTest(deserialize=deserialize, value=value):
                    graph = parse_workflow(workflow)
                    payload = json.dumps({"value": value}) if deserialize else value
                    propagate_workflow_output(graph, graph[0], "workflow:value", payload)
                    result = run_scheduled_workflow(graph, 0)["result"]
                    self.assertEqual(result, value)
                    self.assertIs(type(result), type(value))
        for payload in ('{"value":true}', '{"value":"12"}', '{"value":null}',
                        '{"value":NaN}', '{"value":Infinity}', '{"value":1e400}'):
            with self.subTest(payload=payload), self.assertRaisesRegex(ValueError, "type mismatch"):
                graph = parse_workflow(workflow_fixture(True))
                propagate_workflow_output(graph, graph[0], "workflow:value", payload)
                run_scheduled_workflow(graph, 0)

    def test_number_cannot_connect_to_content(self):
        workflow = workflow_fixture()
        workflow["output_ports"][0]["type"] = "content"
        workflow["nodes"][-1]["workflowPorts"][0]["type"] = "content"
        with self.assertRaises(WorkflowValidationError):
            validate_workflow(workflow)

    def test_current_schema_copies_stay_in_sync(self):
        root = Path(__file__).resolve().parents[1]
        schemas = [json.loads((root / directory / "workflow_2_0.schema.json").read_text(encoding="utf-8"))
                   for directory in ("agent", "manager_webui", "docs/protocol")]
        self.assertEqual(schemas[0], schemas[1])
        self.assertEqual(schemas[0], schemas[2])

    def test_typed_tools_keep_number_arguments_and_results(self):
        fake_tool = types.ModuleType("tools.tool")
        for kind, output_name in (("local", "value"), ("remote", "value"), ("remote", "result")):
            for value in (0, -1.25, True, "3", float("nan"), float("inf")):
                with self.subTest(kind=kind, output_name=output_name, value=value):
                    node = {"id": "tool", "type": "tool", "successors": {"next": 1},
                            "arguments": {"tool": "numeric", "parameters": [{"name": "value", "type": "number"}],
                                          "outputs": [{"name": output_name, "type": "number"}]},
                            "data_inputs": {"value": [None, None, value]},
                            "data_outputs": {output_name: [[1, "value"]]}}
                    graph = [node, {"data_inputs": {"value": [0, output_name, None]}}]
                    if is_number_value(value):
                        self.assertEqual(_tool_arguments(node), {"value": value})
                    else:
                        with self.assertRaisesRegex(ValueError, "must match number"):
                            _tool_arguments(node)
                    result = value if output_name == "result" else {output_name: value}
                    fake_tool.execute_tool = Mock(return_value=result)
                    with patch.dict("sys.modules", {"tools.tool": fake_tool}), \
                         patch("workflow_nodes._call_remote_node", return_value=result):
                        handler = workflow_local_tool if kind == "local" else workflow_remote_sync_tool
                        if is_number_value(value):
                            handler(0, graph)
                            self.assertEqual(graph[1]["data_inputs"]["value"][2], value)
                            self.assertIs(type(graph[1]["data_inputs"]["value"][2]), type(value))
                        else:
                            with self.assertRaisesRegex(ValueError, "must match number"):
                                handler(0, graph)
