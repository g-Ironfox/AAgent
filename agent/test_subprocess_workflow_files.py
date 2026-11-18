import copy
import unittest
from unittest.mock import call, patch

from workflow_nodes import workflow_spawn_and_wait_subprocess
from workflow_parser import WorkflowParseError, parse_workflow
from workflow_validator import (
    WorkflowValidationError,
    validate_workflow,
    validate_subprocess_workflow_files,
)


def empty_workflow(name="Parent"):
    return {
        "schema_version": "2.0",
        "name": name,
        "input_ports": [],
        "output_ports": [],
        "nodes": [
            {"id": "in", "type": "input", "workflowPorts": []},
            {"id": "out", "type": "output", "workflowPorts": []},
        ],
        "connections": [{
            "fromId": "in", "fromPortId": "control-out",
            "toId": "out", "toPortId": "control-in", "type": "control",
        }],
    }


def add_child_call(workflow, name="Child.flow"):
    node = {
        "id": "call-child", "type": "spawn_and_wait_subprocess",
        "arguments": {"workflow_file": name},
        "input_ports": [], "output_ports": [],
    }
    workflow["nodes"].insert(1, node)
    workflow["connections"][0]["toId"] = node["id"]
    workflow["connections"].append({
        "fromId": node["id"], "fromPortId": "control-out",
        "toId": "out", "toPortId": "control-in", "type": "control",
    })
    return node


class SubprocessWorkflowFileValidationTest(unittest.TestCase):
    def setUp(self):
        loader = patch("workflow_parser._read_workspace_workflow_by_name")
        self.read = loader.start()
        self.addCleanup(loader.stop)
        self.child = empty_workflow("Child title differs from filename")
        self.read.return_value = self.child
        self.workflow = empty_workflow()
        self.workflow["subprocess_workflow_files"] = [{
            "name": "Child.flow", "input_ports": [], "output_ports": [],
        }]

    def test_matching_declaration_and_multiple_nodes_read_target_once(self):
        node = add_child_call(self.workflow)
        self.workflow["nodes"].append({**node, "id": "another-call"})
        validate_subprocess_workflow_files(self.workflow)
        self.read.assert_called_once_with("Child.flow")

    def test_declaration_and_node_mismatches_report_source_and_values(self):
        original = [
            {"name": "first", "type": "content"},
            {"name": "second", "type": "content"},
        ]
        changed = [
            [{"name": "renamed", "type": "content"}, original[1]],
            [{"name": "first", "type": "message"}, original[1]],
            original[:1],
            [*original, {"name": "third", "type": "content"}],
            list(reversed(original)),
        ]
        for source in ("declaration", "node"):
            for field in ("input_ports", "output_ports"):
                for ports in changed:
                    with self.subTest(source=source, field=field, ports=ports):
                        workflow = empty_workflow()
                        if source == "declaration":
                            snapshot = {"name": "Child.flow", "input_ports": [], "output_ports": []}
                            workflow["subprocess_workflow_files"] = [snapshot]
                        else:
                            snapshot = add_child_call(workflow)
                        snapshot[field] = copy.deepcopy(original)
                        child = empty_workflow("Child")
                        child[field] = copy.deepcopy(ports)
                        self.read.return_value = child
                        with self.assertRaises(WorkflowValidationError) as caught:
                            validate_subprocess_workflow_files(workflow, "Parent.flow")
                        message = str(caught.exception)
                        for detail in ("Parent", "Child.flow", field, "saved=", "actual=", "refresh"):
                            self.assertIn(detail, message)
                        self.assertIn("subprocess_workflow_files[0]" if source == "declaration" else "call-child", message)

    def test_current_declaration_does_not_hide_stale_node_snapshot(self):
        node = add_child_call(self.workflow)
        node["output_ports"] = [{"name": "removed", "type": "content"}]
        with self.assertRaisesRegex(WorkflowValidationError, "call-child.*output_ports"):
            validate_subprocess_workflow_files(self.workflow)

    def test_nodes_without_declarations_are_checked(self):
        self.workflow.pop("subprocess_workflow_files")
        add_child_call(self.workflow)
        validate_subprocess_workflow_files(self.workflow)
        self.child["input_ports"] = [{"name": "new", "type": "content"}]
        with self.assertRaisesRegex(WorkflowValidationError, "call-child.*input_ports"):
            validate_subprocess_workflow_files(self.workflow)

    def test_each_execution_reads_current_interfaces(self):
        validate_subprocess_workflow_files(self.workflow)
        self.child["output_ports"] = [{"name": "added", "type": "content"}]
        with self.assertRaisesRegex(WorkflowValidationError, "output_ports"):
            validate_subprocess_workflow_files(self.workflow)
        self.assertEqual(self.read.call_count, 2)

    def test_missing_or_unreadable_dependency_fails(self):
        for message in ("workflow file not found: Child.flow", "failed to read workspace workflow file"):
            with self.subTest(message=message):
                self.read.side_effect = WorkflowParseError(message)
                with self.assertRaisesRegex(WorkflowParseError, message):
                    validate_subprocess_workflow_files(self.workflow)

    def test_workflow_without_dependencies_and_static_validation_do_not_read(self):
        validate_subprocess_workflow_files(empty_workflow())
        add_child_call(self.workflow)
        validate_workflow(self.workflow)
        self.read.assert_not_called()


class WorkflowDependencyExecutionTest(unittest.TestCase):
    def setUp(self):
        patcher = patch("workflow_run_repository.record_workflow_run")
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_child_checks_own_dependencies_before_parsing_or_running(self):
        parent = empty_workflow()
        add_child_call(parent)
        child = empty_workflow("Child")
        child["subprocess_workflow_files"] = [{
            "name": "Grandchild.flow", "input_ports": [], "output_ports": [],
        }]
        grandchild = empty_workflow("Grandchild")
        grandchild["input_ports"] = [{"name": "added", "type": "content"}]
        with patch(
            "workflow_parser._read_workspace_workflow_by_name", side_effect=[child, grandchild]
        ) as read, patch("workflow_parser.parse_workflow") as parse, patch("workflow_nodes.run_workflow_map") as run:
            with self.assertRaisesRegex(WorkflowValidationError, "Child.flow.*Grandchild.flow.*input_ports"):
                workflow_spawn_and_wait_subprocess(1, parse_workflow(parent))
            read.assert_has_calls([call("Child.flow"), call("Grandchild.flow")])
            parse.assert_not_called()
            run.assert_not_called()

    def test_child_interface_is_rechecked_at_call_time(self):
        parent = empty_workflow()
        add_child_call(parent)
        child = empty_workflow("Child")
        with patch("workflow_parser._read_workspace_workflow_by_name", return_value=child):
            validate_subprocess_workflow_files(parent)
            child["output_ports"] = [{"name": "added", "type": "content"}]
            child["nodes"][-1]["workflowPorts"] = [
                {"id": "workflow:added", "name": "added", "type": "content"},
            ]
            with patch("workflow_nodes.run_workflow_map") as run:
                with self.assertRaisesRegex(WorkflowValidationError, "call-child.*output_ports"):
                    workflow_spawn_and_wait_subprocess(1, parse_workflow(parent))
                run.assert_not_called()



if __name__ == "__main__":
    unittest.main()
