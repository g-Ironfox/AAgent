"""Regression tests for Map construction value inputs."""

import unittest

from workflow_contract import is_valid_connection
from workflow_nodes import workflow_construct_map_content, workflow_output
from workflow_parser import parse_workflow
from workflow_validator import WorkflowValidationError, validate_workflow


def workflow_fixture():
    return {
        "schema_version": "1.6",
        "name": "map_inputs",
        "input_ports": [{"name": "value", "type": "content"}],
        "output_ports": [{"name": "result", "type": "map-content"}],
        "nodes": [
            {"id": "input", "type": "input", "workflowPorts": [
                {"id": "workflow:value", "name": "value", "type": "content"}
            ]},
            {"id": "map", "type": "construct_map_content", "dataInputPorts": ["map-value-in-0"],
             "arguments": {"mappings": [
                 {"key": "fixed", "value": "constant"},
                 {"key": "dynamic", "value_source": "port", "port_id": "map-value-in-0"},
             ]}},
            {"id": "output", "type": "output", "workflowPorts": [
                {"id": "workflow:result", "name": "result", "type": "map-content"}
            ]},
        ],
        "connections": [
            {"fromId": "input", "fromPortId": "control-out", "toId": "map", "toPortId": "control-in", "type": "control"},
            {"fromId": "map", "fromPortId": "control-out", "toId": "output", "toPortId": "control-in", "type": "control"},
            {"fromId": "input", "fromPortId": "workflow:value", "toId": "map", "toPortId": "map-value-in-0", "type": "content"},
            {"fromId": "map", "fromPortId": "map-out", "toId": "output", "toPortId": "workflow:result", "type": "map-content"},
        ],
    }


class MapInputTest(unittest.TestCase):
    def test_fixed_and_port_values_mix_and_execute(self):
        workflow = workflow_fixture()
        validate_workflow(workflow)
        parsed = parse_workflow(workflow)
        parsed[1]["data_inputs"]["map-value-in-0"][2] = "dynamic value"
        self.assertEqual(workflow_construct_map_content(1, parsed), 2)
        workflow_output(2, parsed)
        self.assertEqual(parsed[2]["_workflow_result"], {
            "result": {"fixed": "constant", "dynamic": "dynamic value"}
        })

    def test_empty_string_is_a_valid_port_value(self):
        parsed = parse_workflow(workflow_fixture())
        parsed[1]["data_inputs"]["map-value-in-0"][2] = ""
        workflow_construct_map_content(1, parsed)
        self.assertEqual(parsed[2]["data_inputs"]["workflow:result"][2], {
            "fixed": "constant", "dynamic": ""
        })

    def test_missing_or_non_string_port_value_fails(self):
        for value in (None, 1, False, {}, []):
            with self.subTest(value=value):
                parsed = parse_workflow(workflow_fixture())
                parsed[1]["data_inputs"]["map-value-in-0"][2] = value
                with self.assertRaises(ValueError):
                    workflow_construct_map_content(1, parsed)
                self.assertIsNone(parsed[2]["data_inputs"]["workflow:result"][2])

    def test_legacy_fixed_mappings_remain_valid(self):
        workflow = workflow_fixture()
        workflow["nodes"][1].pop("dataInputPorts")
        workflow["nodes"][1]["arguments"]["mappings"] = [
            {"key": "legacy", "value": "value"}
        ]
        workflow["connections"].pop(2)
        validate_workflow(workflow)
        parsed = parse_workflow(workflow)
        workflow_construct_map_content(1, parsed)
        self.assertEqual(parsed[2]["data_inputs"]["workflow:result"][2], {
            "legacy": "value"
        })

    def test_rejects_invalid_port_metadata_and_data_types(self):
        invalid = workflow_fixture()
        invalid["nodes"][1]["dataInputPorts"] = ["other"]
        with self.assertRaises(WorkflowValidationError):
            validate_workflow(invalid)

        connection = workflow_fixture()["connections"][2]
        connection["type"] = "message"
        self.assertFalse(is_valid_connection(
            connection,
            {node["id"]: node for node in workflow_fixture()["nodes"]},
            workflow_fixture()["input_ports"],
            workflow_fixture()["output_ports"],
        ))


if __name__ == "__main__":
    unittest.main()
