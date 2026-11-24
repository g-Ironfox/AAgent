import unittest

from unittest.mock import patch

from process import Process, TerminalProcess, WorkflowProcess
from process_repository import spawn_child_and_suspend_parent


class ProcessModelTests(unittest.TestCase):
    def test_record_deserializes_to_typed_process_and_serializes_fields(self):
        process = Process.from_record({
            "process_id": "workflow-1", "process_type": "workflow", "status": "ready",
            "workflow_name": "Root.flow",
        })
        self.assertIsInstance(process, WorkflowProcess)
        self.assertEqual(process.process_id, "workflow-1")
        self.assertEqual(process.workflow_name, "Root.flow")
        self.assertEqual(process.to_record()["process_type"], "workflow")

    def test_wake_requires_matching_wait_source(self):
        process = WorkflowProcess(
            process_id="workflow-1", process_type="workflow", status="blocked",
            wait_for={"kind": "process_exit", "process_id": "child-1"},
        )
        self.assertFalse(process.wake("other-child", "process_exit"))
        self.assertEqual(process.status, "blocked")
        self.assertTrue(process.wake("child-1", "process_exit"))
        self.assertEqual(process.status, "ready")
        self.assertIsNone(process.wait_for)
        self.assertEqual(process.events[-1]["event"], "woken")

    def test_terminal_queue_operations_are_process_local(self):
        terminal = TerminalProcess(
            process_id="terminal-1", process_type="terminal", status="waiting_for_input",
        )
        terminal.enqueue_input("hello")
        self.assertEqual(terminal.drain_input(), ["hello"])
        self.assertEqual(terminal.input_queue, [])

    def test_spawn_lifecycle_requires_parent_to_wait_for_child(self):
        parent = WorkflowProcess(
            process_id="parent", process_type="workflow", root_process_id="parent",
            status="ready",
        )
        child = WorkflowProcess(
            process_id="child", process_type="workflow", root_process_id="parent",
            parent_process_id="parent", terminal_id="session", status="ready",
        )
        terminal = TerminalProcess(
            process_id="child-terminal", process_type="terminal",
            parent_process_id="child", terminal_id="session",
            root_process_id="parent", status="waiting_for_input",
        )
        with patch("process_repository._commit_execution_transition", return_value=parent) as commit:
            client = object()
            result = spawn_child_and_suspend_parent(client, parent, child, terminal)
        self.assertIs(result, parent)
        self.assertEqual(parent.status, "blocked")
        self.assertEqual(parent.wait_for, {"kind": "process_exit", "process_id": "child"})
        commit.assert_called_once_with(client, parent, child, terminal)

    def test_terminal_process_cannot_be_claimed_as_workflow(self):
        terminal = TerminalProcess(
            process_id="terminal-1", process_type="terminal", status="ready",
        )
        with self.assertRaisesRegex(ValueError, "terminal processes are passive"):
            terminal.mark_running("execution-1")


if __name__ == "__main__":
    unittest.main()
