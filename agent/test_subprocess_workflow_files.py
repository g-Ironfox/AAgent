"""Dynamic JSON subprocess contracts and deferred execution."""
import copy
import json
import unittest
from unittest.mock import patch

from workflow_contract import migrate_subprocess_workflow_format
from workflow_nodes import WorkflowStep, current_workflow_process, workflow_spawn_and_wait_subprocess
from workflow_parser import WorkflowParseError, parse_workflow
from workflow_validator import WorkflowValidationError, validate_workflow


def empty_workflow(name="Parent"):
    return {
        "schema_version": "2.0", "name": name, "input_ports": [], "output_ports": [],
        "nodes": [{"id": "in", "type": "input", "workflowPorts": []}, {"id": "out", "type": "output", "workflowPorts": []}],
        "connections": [{"fromId": "in", "fromPortId": "control-out", "toId": "out", "toPortId": "control-in", "type": "control"}],
    }


def add_child_call(workflow, name="Child.flow"):
    node = {"id": "call-child", "type": "spawn_and_wait_subprocess", "arguments": {}}
    workflow["nodes"].insert(1, node)
    workflow["input_ports"] = [{"name": name, "type": "content"} for name in ("file", "arguments")]
    workflow["output_ports"] = [{"name": "result", "type": "content"}]
    workflow["nodes"][0]["workflowPorts"] = [{"id": "workflow:" + p["name"], **p} for p in workflow["input_ports"]]
    workflow["nodes"][-1]["workflowPorts"] = [{"id": "workflow:" + p["name"], **p} for p in workflow["output_ports"]]
    workflow["connections"][0]["toId"] = node["id"]
    for source, output, target, input_port, kind in [
        (node["id"], "control-out", "out", "control-in", "control"),
        ("in", "workflow:file", node["id"], "workflow-file", "content"),
        ("in", "workflow:arguments", node["id"], "arguments-json", "content"),
        (node["id"], "result-json", "out", "workflow:result", "content"),
    ]:
        workflow["connections"].append({"fromId": source, "fromPortId": output, "toId": target, "toPortId": input_port, "type": kind})
    return node


class SubprocessWorkflowTest(unittest.TestCase):
    def setUp(self):
        token = current_workflow_process.set({"process_id": "parent", "invocation_id": "parent"})
        self.addCleanup(current_workflow_process.reset, token)
        self.parent = empty_workflow()
        add_child_call(self.parent)
        self.graph = parse_workflow(self.parent)
        self.graph[1]["_workflow_call_stack"] = ["Parent.flow"]
        self.set_inputs()
        loader = patch("workflow_parser._read_workspace_workflow_by_name", return_value=empty_workflow("Child"))
        self.read = loader.start()
        self.addCleanup(loader.stop)

    def set_inputs(self, filename="Child.flow", arguments="{}"):
        self.graph[1]["data_inputs"]["workflow-file"][2] = filename
        self.graph[1]["data_inputs"]["arguments-json"][2] = arguments

    def execute(self):
        child = self.read.return_value
        for node in child["nodes"]:
            if node["type"] in {"input", "output"}:
                node["workflowPorts"] = [{"id": "workflow:" + p["name"], **p} for p in child[node["type"] + "_ports"]]
        return workflow_spawn_and_wait_subprocess(1, self.graph)

    def test_static_validation_needs_no_declarations_or_workspace_reads(self):
        validate_workflow(self.parent)
        self.read.assert_not_called()
        self.assertEqual(set(self.graph[1]["data_inputs"]), {"workflow-file", "arguments-json"})
        self.assertEqual(set(self.graph[1]["data_outputs"]), {"result-json"})

    def test_removed_declarations_are_discarded_without_mutation(self):
        source = copy.deepcopy(self.parent)
        source["subprocess_workflow_files"] = [{"name": "obsolete.flow"}]
        source["workflow_nodes"] = [{"name": "another.flow"}]
        before = copy.deepcopy(source)
        canonical = migrate_subprocess_workflow_format(source)
        self.assertNotIn("subprocess_workflow_files", canonical)
        self.assertNotIn("workflow_nodes", canonical)
        self.assertEqual(source, before)
        validate_workflow(canonical)

    def test_old_fixed_arguments_and_interface_snapshots_are_rejected(self):
        for field, value in (("arguments", {"workflow_file": "Child.flow"}), ("input_ports", []), ("output_ports", [])):
            with self.subTest(field=field):
                doc = copy.deepcopy(self.parent)
                doc["nodes"][1][field] = value
                with self.assertRaises(WorkflowValidationError):
                    validate_workflow(doc)

    def test_child_execution_is_deferred_and_tracks_ancestry(self):
        with patch("workflow_nodes.execute_node") as execute:
            step = self.execute()
        self.read.assert_called_once_with("Child.flow")
        execute.assert_not_called()
        self.assertIsInstance(step, WorkflowStep)
        child = step.child_process
        self.assertEqual(step.wait_for, {"kind": "process_exit", "process_id": child["process_id"]})
        self.assertEqual(child["parent_process_id"], "parent")
        self.assertEqual(child["ancestor_invocation_ids"], ["parent"])
        self.assertEqual(child["call_stack"], ["Parent.flow", "Child.flow"])
        self.assertEqual(child["current_node_id"], -1)

    def test_filename_is_dynamic_and_keeps_exact_workspace_identity(self):
        self.set_inputs("其他文件.flow")
        self.assertEqual(self.execute().child_process["workflow_file"], "其他文件.flow")
        self.read.assert_called_once_with("其他文件.flow")

    def test_arguments_are_validated_against_current_target_and_copied_to_input(self):
        ports = [{"name": "items", "type": "list-content"}, {"name": "limit", "type": "number"}]
        self.read.return_value["input_ports"] = ports
        self.set_inputs(arguments=json.dumps({"items": ['引号"', "换行\n"], "limit": 3}))
        child = self.execute().child_process
        self.assertEqual(child["input"], {"items": ['引号"', "换行\n"], "limit": 3})
        self.assertEqual(self.graph[1]["data_inputs"]["arguments-json"][2], json.dumps(child["input"]))

    def test_unknown_argument_and_wrong_types_fail_before_child_creation(self):
        self.read.return_value["input_ports"] = [{"name": "count", "type": "number"}]
        for arguments in ('{"other": 1}', '{"count": "bad"}', '{"count": true}', '{"count": NaN}'):
            with self.subTest(arguments=arguments):
                self.set_inputs(arguments=arguments)
                with self.assertRaises(ValueError):
                    self.execute()

    def test_missing_optional_arguments_remain_unset(self):
        self.read.return_value["input_ports"] = [{"name": "count", "type": "number"}]
        self.assertEqual(self.execute().child_process["input"], {"count": None})

    def test_invalid_call_inputs_fail_before_loading_target(self):
        for filename, arguments in ((None, "{}"), (" ", "{}"), ("a" * 201, "{}"), ("Child.flow", None), ("Child.flow", "[]"), ("Child.flow", "null"), ("Child.flow", "bad")):
            with self.subTest(filename=filename, arguments=arguments):
                self.set_inputs(filename, arguments)
                with self.assertRaises(ValueError):
                    self.execute()
        self.read.assert_not_called()

    def test_recursion_is_rejected_before_loading_target(self):
        self.set_inputs("Parent.flow")
        with self.assertRaisesRegex(ValueError, "recursive workflow call"):
            self.execute()
        self.read.assert_not_called()

    def test_missing_target_propagates_loader_error(self):
        self.read.side_effect = WorkflowParseError("workflow file not found")
        with self.assertRaisesRegex(WorkflowParseError, "file not found"):
            self.execute()

    def test_missing_scheduler_fails_before_loading_target(self):
        token = current_workflow_process.set(None)
        try:
            with self.assertRaisesRegex(ValueError, "requires the process scheduler"):
                self.execute()
        finally:
            current_workflow_process.reset(token)
        self.read.assert_not_called()


if __name__ == "__main__":
    unittest.main()
