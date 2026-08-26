import unittest

from workflow_parser import parse_workflow
from workflow_validator import WorkflowValidationError, validate_workflow


def callable_workflow_fixture() -> dict:
    return {
        "nodes": [
            {
                "id": "input",
                "type": "input",
                "name": "Input",
                "workflowPorts": [{"id": "workflow:query", "name": "query", "type": "content"}],
            },
            {
                "id": "call-summary",
                "type": "workflow",
                "name": "Summary",
                "workflow_id": "507f1f77bcf86cd799439011",
                "workflow_name": "Summary",
                "input_ports": [{"name": "query", "type": "content"}],
                "output_ports": [{"name": "result", "type": "content"}],
            },
            {
                "id": "output",
                "type": "output",
                "name": "Output",
                "workflowPorts": [{"id": "workflow:result", "name": "result", "type": "content"}],
            },
        ],
        "connections": [
            {"id": "control-input-call", "fromId": "input", "fromPortId": "control-out", "toId": "call-summary", "toPortId": "control-in", "type": "control"},
            {"id": "control-call-output", "fromId": "call-summary", "fromPortId": "control-out", "toId": "output", "toPortId": "control-in", "type": "control"},
            {"id": "query-input-call", "fromId": "input", "fromPortId": "workflow:query", "toId": "call-summary", "toPortId": "workflow:query", "type": "content"},
            {"id": "result-call-output", "fromId": "call-summary", "fromPortId": "workflow:result", "toId": "output", "toPortId": "workflow:result", "type": "content"},
        ],
    }


class CallableWorkflowNodeTest(unittest.TestCase):
    def test_validator_and_parser_accept_callable_workflow_ports(self):
        workflow = callable_workflow_fixture()

        validate_workflow(workflow)
        parsed = parse_workflow(workflow)

        self.assertEqual(parsed[1]["data_inputs"]["workflow:query"], [0, "workflow:query"])
        self.assertEqual(parsed[1]["data_outputs"]["workflow:result"], [[2, "workflow:result"]])
        self.assertEqual(parsed[1]["workflow_id"], "507f1f77bcf86cd799439011")

    def test_validator_rejects_wrong_callable_workflow_port_type(self):
        workflow = callable_workflow_fixture()
        workflow["connections"][2]["type"] = "message"

        with self.assertRaises(WorkflowValidationError):
            validate_workflow(workflow)

    def test_validator_rejects_multiple_input_nodes(self):
        workflow = callable_workflow_fixture()
        workflow["nodes"].append({
            "id": "input-duplicate",
            "type": "input",
            "name": "Input duplicate",
            "workflowPorts": [],
        })

        with self.assertRaisesRegex(WorkflowValidationError, "exactly one input"):
            validate_workflow(workflow)

    def test_validator_rejects_duplicate_callable_input_port_names(self):
        workflow = callable_workflow_fixture()
        workflow["nodes"][1]["input_ports"].append({"name": " Query ", "type": "message"})

        with self.assertRaisesRegex(WorkflowValidationError, "input_ports contains duplicate names"):
            validate_workflow(workflow)

    def test_validator_rejects_duplicate_callable_output_port_names(self):
        workflow = callable_workflow_fixture()
        workflow["nodes"][1]["output_ports"].append({"name": "RESULT", "type": "message"})

        with self.assertRaisesRegex(WorkflowValidationError, "output_ports contains duplicate names"):
            validate_workflow(workflow)

    def test_validator_allows_same_name_on_input_and_output(self):
        workflow = callable_workflow_fixture()
        workflow["nodes"][1]["output_ports"] = [{"name": "query", "type": "content"}]
        workflow["connections"][3]["fromPortId"] = "workflow:query"

        validate_workflow(workflow)


if __name__ == "__main__":
    unittest.main()