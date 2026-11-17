"""List length validates typed inputs and produces a numeric workflow output."""
import copy
import json
import unittest

from workflow_contract import data_ports_for_node, data_type_for_port
from workflow_nodes import propagate_workflow_output, run_workflow_map, workflow_list_length
from workflow_parser import parse_workflow
from workflow_structs import validate_struct_definitions
from workflow_validator import WorkflowValidationError, _validate_workflow_schema, validate_workflow


TASK = {"id": "task", "name": "Task", "color": "#123456", "list_color": "#654321",
        "fields": [{"name": "name", "type": "content", "required": True}]}


def fixture(value_type="list-content"):
    struct = value_type == "list-struct:task"
    input_type = "content" if struct else value_type
    workflow = {
        "schema_version": "2.0", "name": "list_length", "metadata": {"structs": [TASK]},
        "input_ports": [{"name": "items", "type": input_type}],
        "output_ports": [{"name": "length", "type": "number"}],
        "nodes": [
            {"id": "input", "type": "input", "workflowPorts": [
                {"id": "workflow:items", "name": "items", "type": input_type}]},
            {"id": "length", "type": "list_length", "arguments": {"value_type": value_type}},
            {"id": "output", "type": "output", "workflowPorts": [
                {"id": "workflow:length", "name": "length", "type": "number"}]},
        ], "connections": [],
    }
    source, port = "input", "workflow:items"
    if struct:
        workflow["nodes"].insert(1, {"id": "decode", "type": "json_to_struct",
            "arguments": {"value_type": value_type}, "dataInputPorts": ["content-in"]})
        workflow["connections"].extend([
            {"id": "decode-control", "fromId": "input", "fromPortId": "control-out",
             "toId": "decode", "toPortId": "control-in", "type": "control"},
            {"id": "decode-data", "fromId": "input", "fromPortId": "workflow:items",
             "toId": "decode", "toPortId": "content-in", "type": "content"},
        ])
        source, port = "decode", "value-out"
    workflow["connections"].extend([
        {"id": "length-control", "fromId": source, "fromPortId": "control-out",
         "toId": "length", "toPortId": "control-in", "type": "control"},
        {"id": "length-data", "fromId": source, "fromPortId": port,
         "toId": "length", "toPortId": "list-in", "type": value_type},
        {"id": "output-control", "fromId": "length", "fromPortId": "control-out",
         "toId": "output", "toPortId": "control-in", "type": "control"},
        {"id": "output-data", "fromId": "length", "fromPortId": "length-out",
         "toId": "output", "toPortId": "workflow:length", "type": "number"},
    ])
    return workflow


class WorkflowListLengthTest(unittest.TestCase):
    def test_all_supported_list_types_execute_and_preserve_the_input(self):
        samples = {
            "list-content": ["first", "", "first"],
            "list-message": [{"role": "user", "content": "hello"}, {"role": "assistant", "content": "hi"}],
            "list-struct:task": [{"name": "one"}, {"name": "two"}],
        }
        for value_type, values in samples.items():
            workflow = fixture(value_type)
            validate_workflow(workflow)
            for value in ([], values[:1], values):
                with self.subTest(value_type=value_type, value=value):
                    original = copy.deepcopy(value)
                    graph = parse_workflow(workflow)
                    payload = json.dumps(value) if value_type.startswith("list-struct:") else value
                    propagate_workflow_output(graph, graph[0], "workflow:items", payload)
                    output = run_workflow_map(graph, 0)
                    self.assertEqual(output, {"length": len(value)})
                    self.assertIs(type(output["length"]), int)
                    self.assertEqual(value, original)
                    length = next(node for node in graph if node["id"] == "length")
                    self.assertEqual(length["data_inputs"]["list-in"][2], original)

    def test_missing_nonlist_and_mismatched_elements_do_not_produce_an_output(self):
        for value_type, value in (
            ("list-content", None), ("list-content", "abc"), ("list-content", {"a": "b"}),
            ("list-content", 3), ("list-content", True), ("list-content", [1]),
            ("list-content", ["ok", None]), ("list-message", ["text"]),
            ("list-message", [{"role": "wrong", "content": "text"}]),
            ("list-struct:task", [{}]), ("list-struct:task", [{"name": 1}]),
            ("list-struct:task", [{"name": "ok", "extra": "invalid"}]),
        ):
            with self.subTest(value_type=value_type, value=value):
                node = {"id": "length", "type": "list_length", "arguments": {"value_type": value_type},
                        "_struct_definitions": validate_struct_definitions([TASK]),
                        "data_inputs": {"list-in": [None, None, value]},
                        "data_outputs": {"length-out": [[1, "length"]]}, "successors": {"next": 1}}
                graph = [node, {"data_inputs": {"length": [0, "length-out", None]}}]
                with self.assertRaises(ValueError):
                    workflow_list_length(0, graph)
                self.assertIsNone(graph[1]["data_inputs"]["length"][2])

    def test_type_configuration_is_required_and_only_declared_lists_are_accepted(self):
        for arguments in ({}, {"value_type": "number"}, {"value_type": "content"},
                          {"value_type": "list-number"}, {"value_type": "list-struct:missing"},
                          {"value_type": None}, {"value_type": "list-content", "position": "end"}):
            with self.subTest(arguments=arguments):
                workflow = fixture()
                workflow["nodes"][1]["arguments"] = arguments
                with self.assertRaises(WorkflowValidationError):
                    validate_workflow(workflow)
        workflow = fixture()
        del workflow["nodes"][1]["arguments"]
        with self.assertRaises(WorkflowValidationError):
            _validate_workflow_schema(workflow)

    def test_input_and_output_edge_types_must_match_the_port_contract(self):
        for edge_id, edge_type in (("length-data", "list-message"), ("output-data", "content")):
            with self.subTest(edge_id=edge_id):
                workflow = fixture()
                next(edge for edge in workflow["connections"] if edge["id"] == edge_id)["type"] = edge_type
                with self.assertRaises(WorkflowValidationError):
                    validate_workflow(workflow)

    def test_data_ports_are_fixed_and_report_the_configured_list_type(self):
        for value_type in ("list-content", "list-message", "list-struct:task"):
            node = {"type": "list_length", "arguments": {"value_type": value_type}}
            self.assertEqual(data_ports_for_node(node, [], []), ({"list-in"}, {"length-out"}))
            self.assertEqual(data_type_for_port(node, "list-in"), value_type)
            self.assertEqual(data_type_for_port(node, "length-out"), "number")
            self.assertIsNone(data_type_for_port(node, "unknown"))
