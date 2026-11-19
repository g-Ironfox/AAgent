"""Python-compatible typed list slicing for Workflow 2.0."""
import copy
import json
import itertools
import unittest

from test_workflow_list_length import TASK, fixture as length_fixture
from workflow_contract import data_ports_for_node, data_type_for_port
from test_support import run_scheduled_workflow
from workflow_nodes import propagate_workflow_output
from workflow_parser import parse_workflow
from workflow_validator import WorkflowValidationError, validate_workflow


def fixture(value_type="list-content", bounds=None):
    workflow = copy.deepcopy(length_fixture(value_type))
    workflow["name"] = "list_slice"
    slice_node = next(node for node in workflow["nodes"] if node["id"] == "length")
    slice_node.update(id="slice", type="list_slice")
    measure = {"id": "measure", "type": "list_length", "arguments": {"value_type": value_type}}
    output = next(node for node in workflow["nodes"] if node["id"] == "output")
    workflow["nodes"].insert(workflow["nodes"].index(output), measure)
    for edge in workflow["connections"]:
        if edge["toId"] == "length": edge["toId"] = "slice"
        if edge["fromId"] == "length": edge["fromId"] = "measure"
    workflow["connections"].extend([
        {"id": "slice-measure-control", "fromId": "slice", "fromPortId": "control-out", "toId": "measure", "toPortId": "control-in", "type": "control"},
        {"id": "slice-measure-data", "fromId": "slice", "fromPortId": "list-out", "toId": "measure", "toPortId": "list-in", "type": value_type},
    ])
    for name, value in (bounds or {}).items():
        workflow["input_ports"].append({"name": name, "type": "number"})
        next(node for node in workflow["nodes"] if node["id"] == "input")["workflowPorts"].append(
            {"id": f"workflow:{name}", "name": name, "type": "number"})
        workflow["connections"].append({"id": f"{name}-bound", "fromId": "input", "fromPortId": f"workflow:{name}",
            "toId": "slice", "toPortId": f"{name}-in", "type": "number"})
    return workflow


class WorkflowListSliceTest(unittest.TestCase):
    def execute(self, value_type, values, bounds=None, arguments=None):
        workflow = fixture(value_type, bounds)
        next(node for node in workflow["nodes"] if node["id"] == "slice")["arguments"].update(arguments or {})
        validate_workflow(workflow)
        graph = parse_workflow(workflow)
        payload = json.dumps(values) if value_type.startswith("list-struct:") else values
        propagate_workflow_output(graph, graph[0], "workflow:items", payload)
        for name, value in (bounds or {}).items():
            propagate_workflow_output(graph, graph[0], f"workflow:{name}", value)
        result = run_scheduled_workflow(graph, 0)
        slice_node = next(node for node in graph if node["id"] == "slice")
        sliced = next(node for node in graph if node["id"] == "measure")["data_inputs"]["list-in"][2]
        return result, sliced

    def test_default_slicing_and_typed_lists(self):
        samples = {
            "list-content": ["zero", "one", "two", "three", "four"],
            "list-message": [{"role": "user", "content": str(index)} for index in range(5)],
            "list-struct:task": [{"name": str(index)} for index in range(5)],
        }
        for value_type, values in samples.items():
            for bounds in ({}, {"start": 1, "stop": 4}, {"start": -4, "stop": -1, "step": 2}, {"start": 4, "stop": 0, "step": -2}, {"start": 100}, {"start": 3, "stop": 2}):
                with self.subTest(value_type=value_type, bounds=bounds):
                    original = copy.deepcopy(values)
                    result, sliced = self.execute(value_type, values, bounds)
                    self.assertEqual(sliced, values[slice(bounds.get("start"), bounds.get("stop"), bounds.get("step"))])
                    self.assertEqual(result, {"length": len(sliced)})
                    self.assertEqual(values, original)
                    if sliced and isinstance(sliced[0], (dict, list)):
                        first_index = list(range(len(values)))[slice(bounds.get("start"), bounds.get("stop"), bounds.get("step"))][0]
                        self.assertIsNot(sliced[0], values[first_index])

    def test_optional_numeric_ports_and_type_contract(self):
        node = {"type": "list_slice", "arguments": {"value_type": "list-content"}}
        self.assertEqual(data_ports_for_node(node, [], []), ({"list-in", "start-in", "stop-in", "step-in"}, {"list-out"}))
        self.assertEqual(data_type_for_port(node, "list-in"), "list-content")
        self.assertEqual(data_type_for_port(node, "list-out"), "list-content")
        for port in ("start-in", "stop-in", "step-in"):
            self.assertEqual(data_type_for_port(node, port), "number")
        self.assertIsNone(data_type_for_port(node, "unknown"))
        validate_workflow(fixture())
        for value_type in ("content", "number", "list-number", "list-struct:missing"):
            workflow = fixture()
            next(node for node in workflow["nodes"] if node["id"] == "slice")["arguments"]["value_type"] = value_type
            with self.subTest(value_type=value_type), self.assertRaises(WorkflowValidationError):
                validate_workflow(workflow)

    def test_invalid_slice_bounds_and_zero_step_fail(self):
        for bound, value in (("start", 1.5), ("stop", True), ("step", "2"), ("step", 0)):
            with self.subTest(bound=bound, value=value):
                with self.assertRaisesRegex(ValueError, "list_slice"):
                    self.execute("list-content", ["a", "b", "c"], {bound: value})

    def test_list_input_is_required_and_validated(self):
        for values in (None, "abc", 3, [1, None]):
            with self.subTest(values=values), self.assertRaises(ValueError):
                self.execute("list-content", values)

    def test_slice_schema_rejects_unknown_arguments(self):
        workflow = fixture()
        next(node for node in workflow["nodes"] if node["id"] == "slice")["arguments"]["unknown"] = 2
        with self.assertRaises(WorkflowValidationError):
            validate_workflow(workflow)


    def test_each_bound_can_independently_use_a_fixed_value_or_port(self):
        samples = {
            "list-content": [str(index) for index in range(6)],
            "list-message": [{"role": "user", "content": str(index)} for index in range(6)],
            "list-struct:task": [{"name": str(index)} for index in range(6)],
        }
        for value_type, values in samples.items():
            for sources in itertools.product(("port", "fixed"), repeat=3):
                for bounds in ({"start": 1, "stop": 5, "step": 2}, {"start": -1, "stop": 0, "step": -2}):
                    with self.subTest(value_type=value_type, sources=sources, bounds=bounds):
                        arguments, ports = {}, {}
                        for (name, value), source in zip(bounds.items(), sources):
                            arguments[f"{name}_source"] = source
                            if source == "fixed": arguments[name] = value
                            else: ports[name] = value
                        result, sliced = self.execute(value_type, values, ports, arguments)
                        self.assertEqual(sliced, values[slice(*bounds.values())])
                        self.assertEqual(result, {"length": len(sliced)})

    def test_empty_fixed_bounds_use_python_defaults(self):
        for explicit_null in (False, True):
            arguments = {f"{name}_source": "fixed" for name in ("start", "stop", "step")}
            if explicit_null: arguments.update(start=None, stop=None, step=None)
            self.assertEqual(self.execute("list-content", ["a", "b"], arguments=arguments)[1], ["a", "b"])
        self.assertEqual(self.execute("list-content", ["a", "b"], arguments={"step_source": "fixed", "step": -1.0})[1], ["b", "a"])

    def test_fixed_bounds_hide_ports_and_reject_connections(self):
        for name in ("start", "stop", "step"):
            workflow = fixture(bounds={name: 1})
            node = next(node for node in workflow["nodes"] if node["id"] == "slice")
            node["arguments"].update({f"{name}_source": "fixed", name: 1})
            self.assertNotIn(f"{name}-in", data_ports_for_node(node, [], [])[0])
            self.assertIsNone(data_type_for_port(node, f"{name}-in"))
            with self.assertRaises(WorkflowValidationError): validate_workflow(workflow)

    def test_invalid_fixed_bounds_fail_validation(self):
        for name in ("start", "stop", "step"):
            for value in (True, 1.5, "2", [], {}):
                with self.subTest(name=name, value=value):
                    with self.assertRaises(WorkflowValidationError):
                        self.execute("list-content", [], arguments={f"{name}_source": "fixed", name: value})
            with self.assertRaises(WorkflowValidationError):
                self.execute("list-content", [], arguments={f"{name}_source": "unknown"})
        with self.assertRaises(WorkflowValidationError):
            self.execute("list-content", [], arguments={"step_source": "fixed", "step": 0})
