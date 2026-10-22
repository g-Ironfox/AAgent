import unittest

from pydantic import ValidationError

from workflows import (
    WORKFLOW_SCHEMA_VERSION,
    WorkflowMetadataPatchRequest,
    WorkflowNodeReference,
    WorkflowRequest,
    workflow_port_values,
)
from workflow_node_remap import remap_workflow_node_names
from workflow_validator import WorkflowValidationError, _validate_node, _validate_workflow_schema, validate_workflow
from workflow_structs import StructValidationError, validate_struct_definitions


class WorkflowSchemaVersionTest(unittest.TestCase):
    def test_current_workflow_schema_version_is_2_0(self):
        self.assertEqual(WORKFLOW_SCHEMA_VERSION, "2.0")

    def test_workflow_names_reject_empty_but_preserve_whitespace(self):
        with self.assertRaises(ValidationError):
            WorkflowRequest.model_validate({"name": "", "schema_version": WORKFLOW_SCHEMA_VERSION})

        payload = {
            "name": "   ",
            "schema_version": WORKFLOW_SCHEMA_VERSION,
            "input_ports": [],
            "output_ports": [],
            "nodes": [{"id": "output", "type": "output", "workflowPorts": []}],
        }
        self.assertEqual(WorkflowRequest.model_validate(payload).name, "   ")
        self.assertEqual(WorkflowMetadataPatchRequest(name="  ").name, "  ")

    def test_accepts_current_version_and_rejects_past_and_future_versions(self):
        payload = {
            "name": "echo",
            "schema_version": WORKFLOW_SCHEMA_VERSION,
            "input_ports": [],
            "output_ports": [],
            "nodes": [{"id": "output", "type": "output", "workflowPorts": []}],
        }
        self.assertEqual(
            WorkflowRequest.model_validate(payload).schema_version,
            WORKFLOW_SCHEMA_VERSION,
        )

        without_version = {key: value for key, value in payload.items() if key != "schema_version"}
        with self.assertRaises(ValidationError) as raised:
            WorkflowRequest.model_validate(without_version)
        self.assertEqual(raised.exception.errors()[0]["loc"], ("schema_version",))

        for version in ("1.0", "1.1", "1.4", "1.5", "1.6", "1.8"):
            with self.subTest(version=version):
                with self.assertRaises(ValidationError) as raised:
                    WorkflowRequest.model_validate({**payload, "schema_version": version})
                self.assertEqual(raised.exception.errors()[0]["loc"], ("schema_version",))


class WorkflowNodeRemapTest(unittest.TestCase):
    def test_dependency_rename_preserves_whitespace_in_name(self):
        nodes = [
            {"id": "call-child", "type": "workflow", "arguments": {"workflow_name": "Old child"}},
        ]
        references = [{"name": "  New child  ", "previous_name": "Old child"}]

        remapped = remap_workflow_node_names(nodes, references)

        self.assertEqual(remapped[0]["arguments"]["workflow_name"], "  New child  ")

    def test_metadata_patch_preserves_declared_dependency_ports(self):
        payload = WorkflowMetadataPatchRequest.model_validate({
            "name": "Parent",
            "workflow_nodes": [{
                "name": "Child",
                "input_ports": [{"name": "prompt", "type": "content"}],
                "output_ports": [{"name": "answer", "type": "content"}],
            }],
        })

        reference = payload.workflow_nodes[0].model_dump(exclude_none=True)

        self.assertEqual(
            workflow_port_values(reference["input_ports"]),
            [{"name": "prompt", "type": "content"}],
        )
        self.assertEqual(
            workflow_port_values(reference["output_ports"]),
            [{"name": "answer", "type": "content"}],
        )


class StructJsonConversionValidationTest(unittest.TestCase):
    def test_struct_names_are_unique_case_insensitively(self):
        first = {"id": "profile", "name": "profile", "color": "#3A7D68", "fields": []}
        for duplicate in (first, {**first, "id": "PROFILE", "name": "PROFILE"}):
            with self.subTest(duplicate=duplicate):
                with self.assertRaises(StructValidationError):
                    validate_struct_definitions([first, duplicate])

    def test_manager_schema_accepts_struct_value_types_for_conversion_nodes(self):
        workflow = {
            "schema_version": "2.0",
            "name": "struct_json_conversion",
            "metadata": {"structs": []},
            "input_ports": [],
            "output_ports": [],
            "nodes": [],
            "connections": [],
        }
        for node_type in ("struct_to_json", "json_to_struct"):
            for value_type in ("struct:profile", "list-struct:profile"):
                with self.subTest(node_type=node_type, value_type=value_type):
                    workflow["nodes"] = [{
                        "id": "convert",
                        "type": node_type,
                        "arguments": {"value_type": value_type},
                    }]
                    _validate_workflow_schema(workflow)

    def test_declared_struct_conversion_nodes_pass_semantic_validation(self):
        structs = validate_struct_definitions([{
            "id": "profile",
            "name": "Profile",
            "color": "#3A7D68",
            "fields": [{"name": "display_name", "type": "content", "required": True}],
        }])
        for node_type in ("struct_to_json", "json_to_struct"):
            for value_type in ("struct:profile", "list-struct:profile"):
                with self.subTest(node_type=node_type, value_type=value_type):
                    _validate_node({
                        "id": "convert",
                        "type": node_type,
                        "arguments": {"value_type": value_type},
                        "dataInputPorts": ["value-in" if node_type == "struct_to_json" else "content-in"],
                    }, 0, structs)

    def test_complete_struct_json_round_trip_passes_manager_workflow_validation(self):
        workflow = {
            "schema_version": "2.0",
            "name": "profile_json_round_trip",
            "metadata": {"structs": [{
                "id": "profile",
                "name": "Profile",
                "color": "#3A7D68",
                "fields": [{"name": "display_name", "type": "content", "required": True}],
            }]},
            "input_ports": [{"name": "display_name", "type": "content"}],
            "output_ports": [{"name": "result", "type": "content"}],
            "nodes": [
                {"id": "input", "type": "input", "workflowPorts": [{"id": "workflow:display_name", "name": "display_name", "type": "content"}]},
                {"id": "construct", "type": "construct_struct", "arguments": {"struct_id": "profile"}, "dataInputPorts": ["display_name"]},
                {"id": "serialize", "type": "struct_to_json", "arguments": {"value_type": "struct:profile"}, "dataInputPorts": ["value-in"]},
                {"id": "parse", "type": "json_to_struct", "arguments": {"value_type": "struct:profile"}, "dataInputPorts": ["content-in"]},
                {"id": "get_name", "type": "struct_get", "arguments": {"struct_id": "profile", "field": "display_name"}, "dataInputPorts": ["struct-in"]},
                {"id": "output", "type": "output", "workflowPorts": [{"id": "workflow:result", "name": "result", "type": "content"}]},
            ],
            "connections": [
                {"fromId": "input", "fromPortId": "control-out", "toId": "construct", "toPortId": "control-in", "type": "control"},
                {"fromId": "construct", "fromPortId": "control-out", "toId": "serialize", "toPortId": "control-in", "type": "control"},
                {"fromId": "serialize", "fromPortId": "control-out", "toId": "parse", "toPortId": "control-in", "type": "control"},
                {"fromId": "parse", "fromPortId": "control-out", "toId": "get_name", "toPortId": "control-in", "type": "control"},
                {"fromId": "get_name", "fromPortId": "control-out", "toId": "output", "toPortId": "control-in", "type": "control"},
                {"fromId": "input", "fromPortId": "workflow:display_name", "toId": "construct", "toPortId": "display_name", "type": "content"},
                {"fromId": "construct", "fromPortId": "struct-out", "toId": "serialize", "toPortId": "value-in", "type": "struct:profile"},
                {"fromId": "serialize", "fromPortId": "content-out", "toId": "parse", "toPortId": "content-in", "type": "content"},
                {"fromId": "parse", "fromPortId": "value-out", "toId": "get_name", "toPortId": "struct-in", "type": "struct:profile"},
                {"fromId": "get_name", "fromPortId": "value-out", "toId": "output", "toPortId": "workflow:result", "type": "content"},
            ],
        }
        for name in ("profile", "Legacy display name"):
            with self.subTest(struct_name=name):
                workflow["metadata"]["structs"][0]["name"] = name
                saved = WorkflowRequest.model_validate(workflow).model_dump()
                validate_workflow(saved)
                self.assertEqual(saved["metadata"], workflow["metadata"])

    def test_conversion_nodes_reject_undeclared_struct_type(self):
        for node_type in ("struct_to_json", "json_to_struct"):
            with self.subTest(node_type=node_type):
                with self.assertRaisesRegex(WorkflowValidationError, "requires a declared Struct type"):
                    _validate_node({
                        "id": "convert",
                        "type": node_type,
                        "arguments": {"value_type": "struct:missing"},
                        "dataInputPorts": ["value-in" if node_type == "struct_to_json" else "content-in"],
                    }, 0, {})


class RouterBranchValidationTest(unittest.TestCase):
    def test_router_fallback_is_not_a_user_branch(self):
        for name in ("fallback", "其它"):
            node = {
                "id": "router", "type": "router",
                "arguments": {"branches": [{"id": "branch$others", "name": name}]},
            }
            with self.subTest(name=name):
                with self.assertRaisesRegex(WorkflowValidationError, "reserves id"):
                    _validate_node(node, 0)

    def test_router_allows_no_user_branches(self):
        _validate_node({"id": "router", "type": "router", "arguments": {"branches": []}}, 0)

    def test_router_allows_user_branch_named_other(self):
        _validate_node({
            "id": "router", "type": "router", "arguments": {"branches": [
                {"id": "route-other", "name": "其它"},
            ]},
        }, 0)

if __name__ == "__main__":
    unittest.main()
