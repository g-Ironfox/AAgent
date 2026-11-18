import copy
import unittest

from pydantic import ValidationError
from workflows import WorkflowPortMetadata, WorkflowRequest
from workflow_structs import StructValidationError, validate_value
from workflow_validator import WorkflowValidationError, validate_workflow


def numeric_workflow():
    port = {"name": "value", "type": "number"}
    boundary = {"id": "workflow:value", **port}
    return {
        "schema_version": "2.0", "name": "numeric_boundary",
        "input_ports": [port], "output_ports": [port],
        "nodes": [{"id": "input", "type": "input", "workflowPorts": [boundary]},
                  {"id": "output", "type": "output", "workflowPorts": [boundary]}],
        "connections": [
            {"id": "control", "fromId": "input", "fromPortId": "control-out",
             "toId": "output", "toPortId": "control-in", "type": "control"},
            {"id": "value", "fromId": "input", "fromPortId": "workflow:value",
             "toId": "output", "toPortId": "workflow:value", "type": "number"},
        ],
    }


class WorkflowNumberTest(unittest.TestCase):
    def test_number_is_accepted_by_request_and_graph_validation(self):
        workflow = numeric_workflow()
        payload = WorkflowRequest.model_validate(workflow)
        self.assertEqual(payload.input_ports[0].type, "number")
        validate_workflow(payload.model_dump(exclude_none=True))

    def test_number_interfaces_are_supported_for_dependencies_and_tools(self):
        workflow = numeric_workflow()
        ports = workflow["input_ports"]
        workflow["subprocess_workflow_files"] = [{"name": "child", "input_ports": ports, "output_ports": ports}]
        workflow["metadata"] = {"tools": [{"name": "numeric", "kind": "remote",
                                           "input_ports": ports, "output_ports": ports}]}
        for kind in ("local", "remote"):
            with self.subTest(kind=kind):
                workflow["metadata"]["tools"][0]["kind"] = kind
                validate_workflow(WorkflowRequest.model_validate(workflow).model_dump(exclude_none=True))

    def test_numeric_struct_fields_reject_boolean_strings_and_nonfinite_values(self):
        definitions = {"metric": {"fields": [{"name": "value", "type": "number", "required": True}]}}
        self.assertEqual(validate_value("struct:metric", {"value": 0}, definitions), {"value": 0})
        for invalid in (True, "12", None, float("nan"), float("inf")):
            with self.subTest(invalid=invalid), self.assertRaises(StructValidationError):
                validate_value("struct:metric", {"value": invalid}, definitions)

    def test_number_does_not_implicitly_connect_to_content(self):
        workflow = copy.deepcopy(numeric_workflow())
        workflow["output_ports"][0] = {"name": "value", "type": "content"}
        workflow["nodes"][1]["workflowPorts"][0] = {"id": "workflow:value", "name": "value", "type": "content"}
        with self.assertRaises(WorkflowValidationError):
            validate_workflow(workflow)
        with self.assertRaises(ValidationError):
            WorkflowPortMetadata(name="values", type="list-number")
