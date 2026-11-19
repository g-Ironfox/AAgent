"""Numeric conversion preserves values and enforces both port types."""
import json
import unittest

from workflow_contract import data_ports_for_node, data_type_for_port
from workflow_nodes import execute_node, propagate_workflow_output
from workflow_parser import parse_workflow
from workflow_validator import WorkflowValidationError, validate_workflow
from test_support import run_scheduled_workflow


def fixture():
    return {
        "schema_version": "2.0", "name": "number_to_content",
        "input_ports": [{"name": "value", "type": "number"}],
        "output_ports": [{"name": "text", "type": "content"}],
        "nodes": [
            {"id": "input", "type": "input", "workflowPorts": [
                {"id": "workflow:value", "name": "value", "type": "number"}]},
            {"id": "convert", "type": "number_to_content", "arguments": {}},
            {"id": "output", "type": "output", "workflowPorts": [
                {"id": "workflow:text", "name": "text", "type": "content"}]},
        ],
        "connections": [
            {"id": "in-control", "fromId": "input", "fromPortId": "control-out",
             "toId": "convert", "toPortId": "control-in", "type": "control"},
            {"id": "in-data", "fromId": "input", "fromPortId": "workflow:value",
             "toId": "convert", "toPortId": "number-in", "type": "number"},
            {"id": "out-control", "fromId": "convert", "fromPortId": "control-out",
             "toId": "output", "toPortId": "control-in", "type": "control"},
            {"id": "out-data", "fromId": "convert", "fromPortId": "content-out",
             "toId": "output", "toPortId": "workflow:text", "type": "content"},
        ],
    }


class WorkflowNumberToContentTest(unittest.TestCase):
    def test_numbers_execute_through_the_scheduler_as_json_number_text(self):
        workflow = fixture()
        validate_workflow(workflow)
        for value, expected in (
            (0, "0"), (-12, "-12"), (0.0, "0.0"), (-0.0, "-0.0"),
            (3.5, "3.5"), (-1.25, "-1.25"), (1e100, "1e+100"),
            (9007199254740993, "9007199254740993"), (10 ** 400, "1" + "0" * 400),
        ):
            with self.subTest(value=value):
                graph = parse_workflow(workflow)
                propagate_workflow_output(graph, graph[0], "workflow:value", value)
                self.assertEqual(run_scheduled_workflow(graph, 0), {"text": expected})
                self.assertEqual(json.loads(expected), value)
                self.assertEqual(graph[1]["data_inputs"]["number-in"][2], value)

    def test_missing_and_invalid_values_fail_without_emitting_output(self):
        for value in (None, True, False, "12", [], {}, float("nan"), float("inf"), -float("inf")):
            with self.subTest(value=value):
                graph = parse_workflow(fixture())
                graph[1]["data_inputs"]["number-in"][2] = value
                with self.assertRaisesRegex(ValueError, "number_to_content number-in"):
                    execute_node(1, graph)
                self.assertIsNone(graph[2]["data_inputs"]["workflow:text"][2])
        graph = parse_workflow(fixture())
        graph[1]["data_inputs"] = {}
        with self.assertRaisesRegex(ValueError, "number-in is missing"):
            execute_node(1, graph)

    def test_ports_are_fixed_and_typed(self):
        node = {"type": "number_to_content", "arguments": {}}
        self.assertEqual(data_ports_for_node(node, [], []), ({"number-in"}, {"content-out"}))
        self.assertEqual(data_type_for_port(node, "number-in"), "number")
        self.assertEqual(data_type_for_port(node, "content-out"), "content")
        self.assertIsNone(data_type_for_port(node, "unknown"))

    def test_wrong_edge_types_ports_and_arguments_are_rejected(self):
        for edge_index, key, value in (
            (1, "type", "content"), (3, "type", "number"),
            (1, "toPortId", "content-in"), (3, "fromPortId", "number-out"),
        ):
            with self.subTest(edge_index=edge_index, key=key, value=value):
                workflow = fixture()
                workflow["connections"][edge_index][key] = value
                with self.assertRaises(WorkflowValidationError):
                    validate_workflow(workflow)
        workflow = fixture()
        workflow["nodes"][1]["arguments"] = {"value_type": "number"}
        with self.assertRaises(WorkflowValidationError):
            validate_workflow(workflow)

    def test_output_fans_out_as_text(self):
        graph = parse_workflow(fixture())
        graph.append({"data_inputs": {"text": [1, "content-out", None]}})
        graph[1]["data_outputs"]["content-out"].append([3, "text"])
        graph[1]["data_inputs"]["number-in"][2] = 42
        self.assertEqual(execute_node(1, graph), 2)
        self.assertEqual(graph[2]["data_inputs"]["workflow:text"][2], "42")
        self.assertEqual(graph[3]["data_inputs"]["text"][2], "42")
