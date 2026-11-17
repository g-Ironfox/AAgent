"""Exercise the actual local registry without Redis or provider credentials."""

import importlib.util
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

from workflow_nodes import workflow_local_tool


class LocalToolRegistryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tools_dir = Path(__file__).with_name("tools")
        spec = importlib.util.spec_from_file_location("_test_local_registry", tools_dir / "tool.py")
        cls.registry = importlib.util.module_from_spec(spec)
        environment = {
            "DEEPSEEK_BASE_URL": "http://provider.test", "DEEPSEEK_API_KEY": "test",
            "KIMI_BASE_URL": "http://provider.test", "KIMI_API_KEY": "test",
            "ZAI_API_KEY": "test", "TAVILY_API_KEYS": "test",
            "BOCHA_BASE_URL": "http://provider.test", "BOCHA_API_KEY": "test",
        }
        with patch.dict("os.environ", environment), patch("queue_client.redis_reset_tools"), \
             patch("queue_client.redis_register_tool"):
            spec.loader.exec_module(cls.registry)
            spec = importlib.util.spec_from_file_location("_test_workspace_registry", tools_dir / "workspace.py")
            cls.workspace = importlib.util.module_from_spec(spec)
            with patch.dict(sys.modules, {"tools.tool": cls.registry}):
                spec.loader.exec_module(cls.workspace)

    def test_terminal_output_is_not_registered_as_a_local_tool(self):
        self.assertNotIn("output_to_terminal", self.registry.tool_handlers)

    def test_unknown_local_tool_raises_in_both_result_modes(self):
        for preserve_result in (False, True):
            with self.subTest(preserve_result=preserve_result):
                with self.assertRaisesRegex(ValueError, "missing.tool"):
                    self.registry.execute_tool("node", "missing.tool", {}, preserve_result=preserve_result)

    def test_unknown_local_node_stops_before_propagating_success(self):
        node = {
            "id": "missing", "type": "local_tool", "arguments": {"tool": "missing.tool", "parameters": []},
            "data_outputs": {"output": [[1, "result"]]}, "successors": {"next": 1},
        }
        target = {"data_inputs": {"result": [0, "output", None]}}
        with patch.dict(sys.modules, {"tools.tool": self.registry}), \
             patch("tool_server_client.call_remote_tool") as remote:
            with self.assertRaisesRegex(ValueError, "missing.tool"):
                workflow_local_tool(0, [node, target])
        self.assertIsNone(target["data_inputs"]["result"][2])
        remote.assert_not_called()

    def test_registered_tool_preserves_arguments_results_and_string_serialization(self):
        result = {"nested": [1, 2]}
        handler = Mock(return_value=result)
        with patch.object(self.registry, "tool_handlers", {"known.tool": handler}):
            self.assertIs(self.registry.execute_tool("node", "known.tool", {"value": 3}, preserve_result=True), result)
            self.assertEqual(json.loads(self.registry.execute_tool("node", "known.tool", {"value": 3})), result)
        handler.assert_called_with(value=3)
        self.assertEqual(handler.call_count, 2)

    def test_registered_parent_lookup_and_restore_can_roll_back_a_branch(self):
        tree = {"head_seq": 12, "items": [
            {"seq": 3, "data": {"parent_seq": None}},
            {"seq": 8, "data": {"parent_seq": 3}},
            {"seq": 12, "data": {"parent_seq": 3}},
        ]}
        restored = {"type": "workspace.restore", "data": {"checkpoint_seq": 3}}
        restored_tree = {**tree, "head_seq": 3}
        with patch.object(self.workspace, "_request", side_effect=[tree, restored, restored_tree]) as request:
            parent = self.registry.execute_tool("parent", "workspace.get_parent_checkpoint", {}, preserve_result=True)
            result = self.registry.execute_tool(
                "restore", "workspace.restore_checkpoint", {"seq": parent["parent_seq"]}, preserve_result=True
            )
            next_parent = self.registry.execute_tool("parent", "workspace.get_parent_checkpoint", {}, preserve_result=True)
        self.assertEqual(next_parent, {"seq": 3, "parent_seq": 0})
        self.assertEqual(result, restored)
        self.assertEqual([call.args for call in request.call_args_list], [
            ("GET", "/checkpoints/tree"), ("POST", "/checkpoints/3/restore"), ("GET", "/checkpoints/tree"),
        ])
        schema = next(schema for schema in self.registry.registered_tools
                      if schema["function"]["name"] == "workspace.get_parent_checkpoint")
        self.assertEqual(schema["function"]["parameters"]["properties"]["seq"]["minimum"], 0)

    def test_parent_lookup_accepts_sequence_from_local_workflow_content_port(self):
        node = {
            "id": "parent", "type": "local_tool",
            "arguments": {"tool": "workspace.get_parent_checkpoint", "parameters": ["seq"]},
            "data_inputs": {"seq": [None, None, "12"]},
            "data_outputs": {"output": [[1, "result"]]}, "successors": {"next": 1},
        }
        target = {"data_inputs": {"result": [0, "output", None]}}
        tree = {"head_seq": 15, "items": [{"seq": 12, "data": {"parent_seq": 3}}]}
        with patch.dict(sys.modules, {"tools.tool": self.registry}), \
             patch.object(self.workspace, "_request", return_value=tree):
            self.assertEqual(workflow_local_tool(0, [node, target]), 1)
        self.assertEqual(json.loads(target["data_inputs"]["result"][2]), {"seq": 12, "parent_seq": 3})

    def test_checkpoint_wrappers_are_executable_registered_local_tools(self):
        calls = {
            "workspace.list_checkpoints": {},
            "workspace.checkpoint_tree": {},
            "workspace.checkpoint_diff": {"seq": 0},
            "workspace.create_checkpoint": {"name": "snapshot"},
            "workspace.restore_checkpoint": {"seq": 0},
        }
        schema_names = {schema["function"]["name"] for schema in self.registry.registered_tools}
        for name, arguments in calls.items():
            with self.subTest(tool=name), patch.object(self.workspace, "_request", return_value={"ok": True}) as request:
                self.assertIn(name, schema_names)
                self.assertEqual(self.registry.execute_tool("node", name, arguments, preserve_result=True), {"ok": True})
                request.assert_called_once()


if __name__ == "__main__":
    unittest.main()
