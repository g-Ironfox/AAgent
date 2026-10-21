import copy
import unittest

from workflow_structs import StructValidationError, validate_struct_definitions, validate_value
from workflow_validator import WorkflowValidationError, _validate_workflow_schema


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
