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


class WorkflowSchemaVersionTest(unittest.TestCase):
    def test_current_workflow_schema_version_is_1_4(self):
        self.assertEqual(WORKFLOW_SCHEMA_VERSION, "1.4")

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

        # 升级 Workflow 协议时，更新两侧样例，确保它们都不是当前版本。
        for version in ("1.0", "1.1"):
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

if __name__ == "__main__":
    unittest.main()