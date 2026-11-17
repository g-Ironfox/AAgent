"""Typed zero-based list lookup, including numeric and bounds validation."""
import copy
import json
import unittest

from test_workflow_list_length import TASK, fixture as length_fixture
from workflow_contract import data_ports_for_node, data_type_for_port
from workflow_nodes import propagate_workflow_output, run_workflow_map, workflow_list_get
from workflow_parser import parse_workflow
from workflow_structs import validate_struct_definitions
from workflow_validator import WorkflowValidationError, validate_workflow


def fixture(value_type="list-content"):
    workflow = copy.deepcopy(length_fixture(value_type))
    workflow["name"] = "list_get"
    workflow["input_ports"].append({"name": "index", "type": "number"})
    workflow["nodes"][0]["workflowPorts"].append({"id": "workflow:index", "name": "index", "type": "number"})
    get = next(node for node in workflow["nodes"] if node["id"] == "length")
    get.update(id="get", type="list_get")
    item_type = value_type.removeprefix("list-")
    output_type = "content" if item_type.startswith("struct:") else item_type
    workflow["output_ports"] = [{"name": "result", "type": output_type}]
    workflow["nodes"][-1]["workflowPorts"] = [{"id": "workflow:result", "name": "result", "type": output_type}]
    for edge in workflow["connections"]:
        if edge["fromId"] == "length": edge["fromId"] = "get"
        if edge["toId"] == "length": edge["toId"] = "get"
        if edge["fromPortId"] == "length-out":
            edge.update(fromPortId="item-out", toPortId="workflow:result", type=item_type)
    if item_type.startswith("struct:"):
        workflow["nodes"].insert(-1, {"id": "encode", "type": "struct_to_json",
            "arguments": {"value_type": item_type}, "dataInputPorts": ["value-in"]})
        for edge in workflow["connections"]:
            if edge["toId"] == "output":
                edge["toId"] = "encode"
                if edge["type"] != "control": edge["toPortId"] = "value-in"
        workflow["connections"].extend([
            {"id": "encode-control", "fromId": "encode", "fromPortId": "control-out", "toId": "output", "toPortId": "control-in", "type": "control"},
            {"id": "encode-data", "fromId": "encode", "fromPortId": "content-out", "toId": "output", "toPortId": "workflow:result", "type": "content"},
        ])
    workflow["connections"].append({"id": "index-data", "fromId": "input", "fromPortId": "workflow:index", "toId": "get", "toPortId": "index-in", "type": "number"})
    return workflow


def direct_graph(value_type, values, index):
    return [{"id": "get", "type": "list_get", "arguments": {"value_type": value_type},
             "_struct_definitions": validate_struct_definitions([TASK]),
             "data_inputs": {"list-in": [None, None, values], "index-in": [None, None, index]},
             "data_outputs": {"item-out": [[1, "result"], [2, "result"]]}, "successors": {"next": 1}},
            {"data_inputs": {"result": [0, "item-out", None]}},
            {"data_inputs": {"result": [0, "item-out", None]}}]


class WorkflowListGetTest(unittest.TestCase):
    def test_lookup_executes_for_each_list_type_and_preserves_inputs(self):
        samples = {
            "list-content": ["first", "", "last"],
            "list-message": [{"role": "user", "content": "hello"}, {"role": "assistant", "content": "hi"}],
            "list-struct:task": [{"name": "first"}, {"name": "last"}],
        }
        for value_type, values in samples.items():
            workflow = fixture(value_type)
            validate_workflow(workflow)
            for index in (0, len(values) - 1, 0.0, float(len(values) - 1)):
                with self.subTest(value_type=value_type, index=index):
                    original = copy.deepcopy(values)
                    graph = parse_workflow(workflow)
                    payload = json.dumps(values) if value_type.startswith("list-struct:") else values
                    propagate_workflow_output(graph, graph[0], "workflow:items", payload)
                    propagate_workflow_output(graph, graph[0], "workflow:index", index)
                    result = run_workflow_map(graph, 0)["result"]
                    if value_type.startswith("list-struct:"): result = json.loads(result)
                    self.assertEqual(result, values[int(index)])
                    self.assertIs(type(result), type(values[int(index)]))
                    self.assertEqual(values, original)
                    get = next(node for node in graph if node["id"] == "get")
                    self.assertEqual(get["data_inputs"]["list-in"][2], original)

    def test_invalid_indices_are_rejected_without_output(self):
        for index in (None, True, False, "0", -1, -1.0, 0.5, float("nan"), float("inf"), -float("inf"), [], {}, 2, 2.0, 10 ** 100, 1e100):
            with self.subTest(index=index):
                graph = direct_graph("list-content", ["a", "b"], index)
                with self.assertRaisesRegex(ValueError, "index"):
                    workflow_list_get(0, graph)
                self.assertIsNone(graph[1]["data_inputs"]["result"][2])
        for values, index in (([], 0), (["one"], 1)):
            with self.subTest(values=values, index=index), self.assertRaisesRegex(ValueError, "out of range"):
                workflow_list_get(0, direct_graph("list-content", values, index))

    def test_missing_lists_and_invalid_elements_are_rejected(self):
        for value_type, values in (
            ("list-content", None), ("list-content", "abc"), ("list-content", 3),
            ("list-content", {"a": "b"}), ("list-content", ["ok", 3]),
            ("list-message", ["text"]), ("list-message", [{"role": "wrong", "content": "text"}]),
            ("list-struct:task", [{}]), ("list-struct:task", [{"name": 1}]),
            ("list-struct:task", [{"name": "ok", "extra": "invalid"}]),
        ):
            with self.subTest(value_type=value_type, values=values):
                graph = direct_graph(value_type, values, 0)
                with self.assertRaises(ValueError): workflow_list_get(0, graph)
                self.assertIsNone(graph[1]["data_inputs"]["result"][2])

    def test_struct_and_message_outputs_are_independent_copies(self):
        for value_type, values in (("list-message", [{"role": "user", "content": "original"}]),
                                   ("list-struct:task", [{"name": "original"}])):
            graph = direct_graph(value_type, values, 0)
            self.assertEqual(workflow_list_get(0, graph), 1)
            first, second = (node["data_inputs"]["result"][2] for node in graph[1:])
            self.assertEqual(first, values[0])
            self.assertIsNot(first, values[0])
            self.assertIsNot(first, second)
            key = "name" if value_type.startswith("list-struct:") else "content"
            first[key] = "changed"
            self.assertEqual(second[key], "original")
            self.assertEqual(values[0][key], "original")

    def test_list_type_is_required_and_must_reference_a_supported_list(self):
        for arguments in (None, {}, {"value_type": "content"}, {"value_type": "number"},
                          {"value_type": "list-number"}, {"value_type": "list-struct:missing"},
                          {"value_type": None}, {"value_type": "list-content", "index_source": "fixed"}):
            with self.subTest(arguments=arguments):
                workflow = fixture()
                get = next(node for node in workflow["nodes"] if node["id"] == "get")
                if arguments is None: del get["arguments"]
                else: get["arguments"] = arguments
                with self.assertRaises(WorkflowValidationError): validate_workflow(workflow)

    def test_input_and_output_edges_match_the_configured_types(self):
        for port, invalid_type in (("list-in", "list-message"), ("index-in", "content"), ("workflow:result", "number")):
            workflow = fixture()
            next(edge for edge in workflow["connections"] if edge["toPortId"] == port)["type"] = invalid_type
            with self.subTest(port=port), self.assertRaises(WorkflowValidationError): validate_workflow(workflow)

    def test_ports_declare_list_numeric_index_and_element_types(self):
        for value_type in ("list-content", "list-message", "list-struct:task"):
            node = {"type": "list_get", "arguments": {"value_type": value_type}}
            self.assertEqual(data_ports_for_node(node, [], []), ({"list-in", "index-in"}, {"item-out"}))
            self.assertEqual(data_type_for_port(node, "list-in"), value_type)
            self.assertEqual(data_type_for_port(node, "index-in"), "number")
            self.assertEqual(data_type_for_port(node, "item-out"), value_type[5:])
            self.assertIsNone(data_type_for_port(node, "unknown"))


class WorkflowListGetIndexSourceTest(unittest.TestCase):
    def test_fixed_index_runs_without_an_index_connection_for_every_list_type(self):
        samples = {
            "list-content": ["first", "last"],
            "list-message": [{"role": "user", "content": "first"}, {"role": "assistant", "content": "last"}],
            "list-struct:task": [{"name": "first"}, {"name": "last"}],
        }
        for value_type, values in samples.items():
            for index in (0, 1, 1.0):
                with self.subTest(value_type=value_type, index=index):
                    workflow = fixture(value_type)
                    get = next(node for node in workflow["nodes"] if node["id"] == "get")
                    get["arguments"].update(index_source="fixed", index=index)
                    workflow["connections"] = [edge for edge in workflow["connections"] if edge["toPortId"] != "index-in"]
                    validate_workflow(workflow)
                    self.assertEqual(data_ports_for_node(get, [], []), ({"list-in"}, {"item-out"}))
                    self.assertIsNone(data_type_for_port(get, "index-in"))
                    graph = parse_workflow(workflow)
                    self.assertNotIn("index-in", next(node for node in graph if node.get("id") == "get")["data_inputs"])
                    payload = json.dumps(values) if value_type.startswith("list-struct:") else values
                    propagate_workflow_output(graph, graph[0], "workflow:items", payload)
                    result = run_workflow_map(graph, 0)["result"]
                    if value_type.startswith("list-struct:"): result = json.loads(result)
                    self.assertEqual(result, values[int(index)])

    def test_fixed_index_takes_precedence_and_copies_outputs(self):
        values = [{"role": "user", "content": "first"}, {"role": "assistant", "content": "last"}]
        graph = direct_graph("list-message", values, 0)
        graph[0]["arguments"].update(index_source="fixed", index=1)
        workflow_list_get(0, graph)
        result = graph[1]["data_inputs"]["result"][2]
        self.assertEqual(result, values[1])
        self.assertIsNot(result, values[1])
        result["content"] = "changed"
        self.assertEqual(values[1]["content"], "last")

    def test_fixed_index_is_validated_at_runtime(self):
        for index in (None, True, False, "0", -1, 0.5, float("nan"), float("inf"), [], {}, 2):
            with self.subTest(index=index):
                graph = direct_graph("list-content", ["a", "b"], 0)
                graph[0]["arguments"].update(index_source="fixed", index=index)
                with self.assertRaisesRegex(ValueError, "index"):
                    workflow_list_get(0, graph)
                self.assertIsNone(graph[1]["data_inputs"]["result"][2])
        graph = direct_graph("list-content", ["a"], 0)
        graph[0]["arguments"]["index_source"] = "fixed"
        with self.assertRaisesRegex(ValueError, "missing"):
            workflow_list_get(0, graph)
        graph[0]["arguments"]["index_source"] = "invalid"
        with self.assertRaisesRegex(ValueError, "index_source"):
            workflow_list_get(0, graph)
        graph = direct_graph("list-content", [], 0)
        graph[0]["arguments"].update(index_source="fixed", index=0)
        with self.assertRaisesRegex(ValueError, "out of range"):
            workflow_list_get(0, graph)

    def test_explicit_port_source_requires_input_and_ignores_fixed_setting(self):
        graph = direct_graph("list-content", ["a", "b"], 1)
        graph[0]["arguments"].update(index_source="port", index=0)
        workflow_list_get(0, graph)
        self.assertEqual(graph[1]["data_inputs"]["result"][2], "b")
        del graph[0]["data_inputs"]["index-in"]
        with self.assertRaisesRegex(ValueError, "missing"):
            workflow_list_get(0, graph)

    def test_fixed_mode_rejects_index_port_connections(self):
        workflow = fixture()
        next(node for node in workflow["nodes"] if node["id"] == "get")["arguments"].update(index_source="fixed", index=0)
        with self.assertRaises(WorkflowValidationError):
            validate_workflow(workflow)

    def test_invalid_index_configuration_is_rejected(self):
        cases = [{"index_source": source} for source in (None, "", "unknown", True)]
        cases += [{"index_source": "fixed"}]
        cases += [{"index_source": "fixed", "index": index} for index in (None, True, False, "0", -1, 0.5, float("nan"), float("inf"), [], {})]
        for arguments in cases:
            with self.subTest(arguments=arguments):
                workflow = fixture()
                next(node for node in workflow["nodes"] if node["id"] == "get")["arguments"].update(arguments)
                workflow["connections"] = [edge for edge in workflow["connections"] if edge["toPortId"] != "index-in"]
                with self.assertRaises(WorkflowValidationError):
                    validate_workflow(workflow)
