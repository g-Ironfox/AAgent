import copy
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

from workflow_contract import migrate_subprocess_workflow_format
from workflow_parser import parse_workflow
from workflow_validator import WorkflowValidationError, validate_workflow
from test_subprocess_workflow_files import empty_workflow, add_child_call

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from migrate_subprocess_workflows import migrate_content, migrate_paths, migrate_workspace, main as migrate_main


def legacy_workflow():
    document = empty_workflow()
    node = add_child_call(document)
    node["type"] = "workflow"
    document["workflow_nodes"] = [{"name": "Child.flow", "input_ports": [], "output_ports": []}]
    return document


class WorkflowFormatMigrationTest(unittest.TestCase):
    def test_workflow_identity_is_external_and_legacy_names_are_removed(self):
        document = empty_workflow()
        document["metadata"] = {"name": "obsolete", "structs": [
            {"id": "profile", "name": "Profile", "color": "#3A7D68", "fields": []}
        ]}
        before = copy.deepcopy(document)
        canonical = migrate_subprocess_workflow_format(document)
        self.assertNotIn("name", canonical)
        self.assertNotIn("name", canonical["metadata"])
        self.assertEqual(canonical["metadata"]["structs"][0]["name"], "Profile")
        self.assertEqual(document, before)
        validate_workflow(canonical)
        parse_workflow(canonical)


    def test_legacy_document_compiles_to_only_new_fields_without_mutation(self):
        original = legacy_workflow()
        before = copy.deepcopy(original)
        canonical = migrate_subprocess_workflow_format(original)
        validate_workflow(canonical)
        compiled = parse_workflow(canonical)
        self.assertEqual(compiled[1]["type"], "spawn_and_wait_subprocess")
        self.assertEqual(compiled[1]["arguments"], {})
        self.assertNotIn("workflow_nodes", canonical)
        self.assertNotIn("subprocess_workflow_files", canonical)
        self.assertEqual(original, before)
        self.assertEqual(migrate_subprocess_workflow_format(canonical), canonical)

    def test_removed_declarations_are_discarded_even_when_they_differ(self):
        original = legacy_workflow()
        original["subprocess_workflow_files"] = []
        canonical = migrate_subprocess_workflow_format(original)
        self.assertNotIn("workflow_nodes", canonical)
        self.assertNotIn("subprocess_workflow_files", canonical)
        validate_workflow(canonical)

    def test_legacy_fixed_call_requires_explicit_json_port_conversion(self):
        original = legacy_workflow()
        original["nodes"][1]["arguments"] = {"workflow_name": "Child.flow"}
        migrated = migrate_subprocess_workflow_format(original)
        with self.assertRaisesRegex(WorkflowValidationError, "unsupported fields: workflow_file"):
            validate_workflow(migrated)

    def test_malformed_nodes_report_validation_errors(self):
        document = empty_workflow()
        document["nodes"] = None
        with self.assertRaises(WorkflowValidationError):
            validate_workflow(document)

    def test_batch_migration_is_idempotent_and_preserves_other_files(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "parent.flow"
            original = json.dumps(legacy_workflow())
            path.write_text(original, encoding="utf8")
            notes = Path(folder) / "notes.json"
            notes.write_text('{"ordinary": true}', encoding="utf8")
            self.assertEqual(migrate_paths([folder]), 1)
            self.assertEqual(path.read_text(encoding="utf8"), original)
            self.assertEqual(migrate_paths([folder], apply=True), 1)
            self.assertEqual(migrate_paths([folder], apply=True), 0)
            self.assertEqual(notes.read_text(encoding="utf8"), '{"ordinary": true}')
            self.assertNotIn("workflow_nodes", json.loads(path.read_text(encoding="utf8")))

    def test_workspace_migration_uses_current_revision_and_does_not_write_in_preview(self):
        file = {"file_id": "f1", "name": "parent.flow", "content": json.dumps(legacy_workflow()), "revision": 7}
        response_list = Mock(); response_list.json.return_value = {"items": [{"file_id": "f1"}]}
        response_file = Mock(); response_file.json.return_value = file
        with patch("requests.get", side_effect=[response_list, response_file]), patch("requests.put") as write:
            self.assertEqual(migrate_workspace("http://workspace"), 1)
            write.assert_not_called()
        with patch("requests.get", side_effect=[response_list, response_file]), patch("requests.put") as write:
            self.assertEqual(migrate_workspace("http://workspace", apply=True), 1)
            payload = write.call_args.kwargs["json"]
            self.assertEqual(payload["revision"], 7)
            self.assertEqual(payload["name"], "parent.flow")
            self.assertNotIn("workflow_nodes", json.loads(payload["content"]))

    def test_removed_manager_option_is_rejected_without_network_requests(self):
        with patch("sys.stderr", new_callable=io.StringIO), \
             patch("requests.get") as read, patch("requests.patch") as write:
            with self.assertRaises(SystemExit) as error:
                migrate_main(["--manager-url", "http://manager"])
        self.assertEqual(error.exception.code, 2)
        read.assert_not_called()
        write.assert_not_called()

    def test_design_envelope_is_migrated_without_renaming_files(self):
        source = {"format": "aagent.workflow-design/1", "entrypoint": "parent.flow", "workflows": [
            {"filename": "parent.flow", "workflow": legacy_workflow()}]}
        migrated = json.loads(migrate_content(json.dumps(source)))
        self.assertEqual(migrated["entrypoint"], source["entrypoint"])
        self.assertEqual(migrated["workflows"][0]["filename"], "parent.flow")
        self.assertEqual(migrated["workflows"][0]["workflow"]["nodes"][1]["type"], "spawn_and_wait_subprocess")


if __name__ == "__main__":
    unittest.main()
