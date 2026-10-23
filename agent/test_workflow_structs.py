import copy
import unittest

from workflow_structs import StructValidationError, validate_struct_definitions, validate_value
from workflow_validator import WorkflowValidationError, _validate_workflow_schema, validate_workflow


def definitions():
    return validate_struct_definitions([
        {"id": "profile", "name": "Profile", "color": "#3A7D68", "fields": [
            {"name": "name", "type": "content", "required": True},
            {"name": "tags", "type": "list-content", "required": False},
        ]},
        {"id": "task", "name": "Task", "color": "#D97706", "fields": [
            {"name": "owner", "type": "struct:profile", "required": True},
            {"name": "reviewers", "type": "list-struct:profile", "required": True},
        ]},
    ])


class WorkflowStructTest(unittest.TestCase):
    def test_list_color_is_independent_and_legacy_definitions_fall_back(self):
        legacy = {"id": "profile", "name": "Profile", "color": "#3A7D68", "fields": []}
        definitions = validate_struct_definitions([legacy, {**legacy, "id": "task", "name": "Task", "list_color": "#3976A8"}])
        self.assertEqual(definitions["profile"]["list_color"], "#3A7D68")
        self.assertEqual(definitions["task"]["list_color"], "#3976A8")

        with self.assertRaises(StructValidationError):
            validate_struct_definitions([{**legacy, "list_color": "green"}])

    def test_struct_names_are_unique_case_insensitively(self):
        first = {"id": "profile", "name": "profile", "color": "#3A7D68", "fields": []}
        for duplicate in (first, {**first, "id": "PROFILE", "name": "PROFILE"}):
            with self.subTest(duplicate=duplicate):
                with self.assertRaises(StructValidationError):
                    validate_struct_definitions([first, duplicate])

    def test_nested_struct_and_struct_list_validate(self):
        defs = definitions()
        value = {"owner": {"name": "Ada"}, "reviewers": [{"name": "Lin", "tags": ["review"]}]}
        self.assertEqual(validate_value("struct:task", value, defs), value)

    def test_missing_required_and_extra_fields_report_paths(self):
        defs = definitions()
        with self.assertRaisesRegex(StructValidationError, r"\$\.owner\.name"):
            validate_value("struct:task", {"owner": {}, "reviewers": []}, defs)
        with self.assertRaisesRegex(StructValidationError, r"\$\.owner\.unexpected"):
            validate_value("struct:task", {"owner": {"name": "Ada", "unexpected": 1}, "reviewers": []}, defs)

    def test_optional_fields_may_be_absent_but_not_null(self):
        defs = definitions()
        self.assertEqual(validate_value("struct:profile", {"name": "Ada"}, defs), {"name": "Ada"})
        with self.assertRaises(StructValidationError):
            validate_value("struct:profile", {"name": "Ada", "tags": None}, defs)

    def test_recursive_values_are_copied_for_context_isolation(self):
        defs = definitions()
        source = {"owner": {"name": "Ada"}, "reviewers": []}
        copied = validate_value("struct:task", source, defs, copy_value=True)
        copied["owner"]["name"] = "Grace"
        self.assertEqual(source["owner"]["name"], "Ada")

    def test_unknown_references_and_cycles_are_rejected(self):
        unknown = [{"id": "a", "name": "A", "color": "#000000", "fields": [{"name": "b", "type": "struct:nope", "required": True}]}]
        cycle = [
            {"id": "a", "name": "A", "color": "#000000", "fields": [{"name": "b", "type": "struct:b", "required": True}]},
            {"id": "b", "name": "B", "color": "#ffffff", "fields": [{"name": "a", "type": "struct:a", "required": True}]},
        ]
        for item in (unknown, cycle):
            with self.assertRaises(StructValidationError):
                validate_struct_definitions(item)

    def test_declared_struct_json_round_trip_executes_in_validated_workflow(self):
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
                {"id": "get_name", "type": "struct_get", "arguments": {"struct_id": "profile", "field": "display_name", "missing": "error", "has_fallback": False}, "dataInputPorts": ["struct-in"]},
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
        from workflow_nodes import propagate_workflow_output, run_workflow_map
        from workflow_parser import parse_workflow

        for name in ("profile", "Legacy display name"):
            with self.subTest(struct_name=name):
                workflow["metadata"]["structs"][0]["name"] = name
                validate_workflow(workflow)
                workflow_map = parse_workflow(workflow)
                self.assertEqual(workflow_map[0]["_struct_definitions"]["profile"]["name"], name)
                propagate_workflow_output(workflow_map, workflow_map[0], "workflow:display_name", "Ada Lovelace")
                self.assertEqual(run_workflow_map(workflow_map, 0), {"result": "Ada Lovelace"})

    def test_json_conversion_schema_accepts_declared_struct_types(self):
        workflow = {
            "schema_version": "2.0",
            "name": "struct_json_conversion",
            "metadata": {"structs": []},
            "input_ports": [],
            "output_ports": [],
            "connections": [],
            "nodes": [],
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

    def test_session_schema_still_rejects_struct_types(self):
        workflow = {
            "schema_version": "2.0",
            "name": "session_struct_rejected",
            "metadata": {"structs": []},
            "input_ports": [],
            "output_ports": [],
            "connections": [],
            "nodes": [{
                "id": "session",
                "type": "session_create",
                "arguments": {"value_type": "struct:profile"},
            }],
        }
        with self.assertRaises(WorkflowValidationError):
            _validate_workflow_schema(workflow)

    def test_context_schema_accepts_local_types_but_session_schema_rejects_them(self):
        workflow = {
            "schema_version": "2.0",
            "name": "context_struct",
            "metadata": {"structs": []},
            "input_ports": [],
            "output_ports": [],
            "nodes": [{
                "id": "context",
                "type": "context_create",
                "arguments": {"value_type": "struct:profile"},
            }],
            "connections": [],
        }
        _validate_workflow_schema(workflow)
        workflow["nodes"][0] = {
            "id": "session",
            "type": "session_create",
            "arguments": {"value_type": "struct:profile"},
        }
        with self.assertRaises(WorkflowValidationError):
            _validate_workflow_schema(workflow)


if __name__ == "__main__":
    unittest.main()
