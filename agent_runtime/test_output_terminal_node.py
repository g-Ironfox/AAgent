import unittest
from unittest.mock import patch

from terminal_repository import current_terminal_process_id, terminal_process_context
from workflow_contract import NODE_ARGUMENT_FIELDS_BY_TYPE, SUPPORTED_NODE_TYPES
from workflow_nodes import nodes_map, workflow_output_to_terminal
from workflow_parser import parse_workflow
from workflow_validator import validate_workflow


class OutputToTerminalNodeTest(unittest.TestCase):
    def test_node_is_registered_as_a_builtin_without_arguments(self):
        self.assertIn("output_to_terminal", SUPPORTED_NODE_TYPES)
        self.assertEqual(NODE_ARGUMENT_FIELDS_BY_TYPE["output_to_terminal"], set())
        self.assertIs(nodes_map["output_to_terminal"], workflow_output_to_terminal)

    def test_validates_and_writes_to_the_current_process_terminal(self):
        document = {
            "schema_version": "2.0", "name": "terminal_output",
            "input_ports": [{"name": "text", "type": "content"}],
            "output_ports": [],
            "nodes": [
                {"id": "input", "type": "input", "workflowPorts": [
                    {"id": "workflow:text", "name": "text", "type": "content"}
                ]},
                {"id": "terminal", "type": "output_to_terminal"},
                {"id": "output", "type": "output", "workflowPorts": []},
            ],
            "connections": [
                {"fromId": "input", "fromPortId": "control-out", "toId": "terminal", "toPortId": "control-in", "type": "control"},
                {"fromId": "terminal", "fromPortId": "control-out", "toId": "output", "toPortId": "control-in", "type": "control"},
                {"fromId": "input", "fromPortId": "workflow:text", "toId": "terminal", "toPortId": "content-in", "type": "content"},
            ],
            "metadata": {"structs": []},
        }
        validate_workflow(document)
        workflow = parse_workflow(document)
        workflow[1]["data_inputs"]["content-in"][2] = "hello"
        with patch("terminal_repository.append_terminal_output") as append:
            with terminal_process_context("internal-terminal-123", "public-terminal-123"):
                next_node = nodes_map["input"](0, workflow)
                self.assertEqual(next_node, 1)
                next_node = workflow_output_to_terminal(next_node, workflow)
        self.assertEqual(next_node, 2)
        append.assert_called_once_with(
            "hello",
            terminal_id="public-terminal-123",
            terminal_process_id="internal-terminal-123",
        )
        self.assertIsNone(current_terminal_process_id.get())

    def test_requires_process_terminal_and_nonempty_text(self):
        node = {
            "id": "terminal", "type": "output_to_terminal",
            "data_inputs": {"content-in": [None, "content", "hello"]},
            "successors": {"next": 1},
        }
        with self.assertRaisesRegex(ValueError, "requires a process terminal"):
            workflow_output_to_terminal(0, [node])
        with terminal_process_context("internal-terminal-123", "public-terminal-123"):
            for value in (None, 4, " "):
                node["data_inputs"]["content-in"][2] = value
                with self.subTest(value=value), self.assertRaisesRegex(ValueError, "non-empty text"):
                    workflow_output_to_terminal(0, [node])


if __name__ == "__main__":
    unittest.main()
