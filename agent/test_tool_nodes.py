import json
import sys
import types
import unittest
from unittest.mock import Mock, patch

import requests

from tool_server_client import ToolServerError, call_remote_tool
from workflow_contract import NODE_ARGUMENT_FIELDS_BY_TYPE, SUPPORTED_NODE_TYPES, is_valid_connection
from workflow_nodes import workflow_local_tool, workflow_remote_async_tool, workflow_remote_sync_tool
from workflow_nodes import nodes_map
from workflow_validator import WorkflowValidationError, validate_workflow


def tool_workflow_map(node_type: str, **arguments) -> list[dict]:
    is_remote = node_type in {"remote_sync_tool", "remote_async_tool"}
    parameters = [{"name": "value", "type": "content"}] if is_remote else ["value"]
    output_port = "task_id" if node_type == "remote_async_tool" else "result"
    if node_type == "remote_sync_tool":
        arguments = {"outputs": [{"name": "result", "type": "content"}], **arguments}
    return [
        {
            "id": "tool-node",
            "type": node_type,
            "arguments": {"tool": "echo", "parameters": parameters, **arguments},
            "successors": {"next": 1},
            "data_inputs": {"value": [None, None, "hello"]},
            "data_outputs": {output_port: [[1, "result"]]},
        },
        {
            "id": "target",
            "data_inputs": {"result": [0, output_port, None]},
            "data_outputs": {},
        },
    ]


def valid_workflow(node: dict) -> dict:
    return {
        "input_ports": [],
        "output_ports": [],
        "nodes": [
            {"id": "input", "type": "input", "workflowPorts": []},
            node,
            {"id": "output", "type": "output", "workflowPorts": []},
        ],
        "connections": [
            {"fromId": "input", "fromPortId": "control-out", "toId": node["id"], "toPortId": "control-in", "type": "control"},
            {"fromId": node["id"], "fromPortId": "control-out", "toId": "output", "toPortId": "control-in", "type": "control"},
        ],
    }


class ToolNodeExecutionTest(unittest.TestCase):
    def test_local_tool_uses_process_executor_and_serializes_result(self):
        execute_tool = Mock()
        execute_tool.return_value = {"ok": True}
        tool_module = types.ModuleType("tools.tool")
        tool_module.execute_tool = execute_tool
        workflow_map = tool_workflow_map("local_tool")

        with patch.dict(sys.modules, {"tools.tool": tool_module}):
            next_id = workflow_local_tool(0, workflow_map)

        self.assertEqual(next_id, 1)
        execute_tool.assert_called_once_with("tool-node", "echo", {"value": "hello"})
        self.assertEqual(workflow_map[1]["data_inputs"]["result"][2], '{"ok": true}')

    @patch("tool_server_client.call_remote_tool")
    def test_remote_sync_tool_uses_client_and_preserves_string_result(self, call_tool):
        call_tool.return_value = "done"
        workflow_map = tool_workflow_map("remote_sync_tool", timeout_ms=2500)

        next_id = workflow_remote_sync_tool(0, workflow_map)

        self.assertEqual(next_id, 1)
        call_tool.assert_called_once_with("echo", {"value": "hello"}, "wait", 2500, None)
        self.assertEqual(workflow_map[1]["data_inputs"]["result"][2], "done")

    @patch("tool_server_client.call_remote_tool")
    def test_remote_sync_tool_distributes_named_outputs(self, call_tool):
        call_tool.return_value = {"answer": "done", "items": ["a", "b"]}
        workflow_map = tool_workflow_map(
            "remote_sync_tool",
            outputs=[
                {"name": "answer", "type": "content"},
                {"name": "items", "type": "list-content"},
            ],
            timeout_ms=2500,
        )
        workflow_map[0]["data_outputs"] = {"answer": [[1, "answer"]], "items": [[1, "items"]]}
        workflow_map[1]["data_inputs"] = {
            "answer": [0, "answer", None],
            "items": [0, "items", None],
        }

        workflow_remote_sync_tool(0, workflow_map)

        self.assertEqual(workflow_map[1]["data_inputs"]["answer"][2], "done")
        self.assertEqual(workflow_map[1]["data_inputs"]["items"][2], ["a", "b"])

    @patch("tool_server_client.call_remote_tool")
    def test_remote_sync_tool_error_includes_task_id(self, call_tool):
        call_tool.side_effect = ToolServerError("still running", task_id="task-1")

        with self.assertRaises(ValueError) as raised:
            workflow_remote_sync_tool(0, tool_workflow_map("remote_sync_tool", timeout_ms=1000))

        details = json.loads(str(raised.exception))
        self.assertEqual(details["execution"], "remote_sync")
        self.assertEqual(details["task_id"], "task-1")

    @patch("tool_server_client.call_remote_tool")
    def test_remote_async_tool_outputs_task_id(self, call_tool):
        call_tool.return_value = "task-7"
        workflow_map = tool_workflow_map("remote_async_tool", timeout_ms=60000)

        next_id = workflow_remote_async_tool(0, workflow_map)

        self.assertEqual(next_id, 1)
        call_tool.assert_called_once_with("echo", {"value": "hello"}, "async", 60000, None)
        self.assertEqual(workflow_map[1]["data_inputs"]["result"][2], "task-7")

    @patch("tool_server_client.call_remote_tool")
    def test_remote_async_tool_submits_callback(self, call_tool):
        call_tool.return_value = "task-8"
        callback = {
            "type": "redis",
            "queue": "main_agent_queue",
            "event_type": "async_result",
            "on": ["completed", "failed"],
        }
        workflow_map = tool_workflow_map(
            "remote_async_tool", timeout_ms=60000, callback=callback
        )

        workflow_remote_async_tool(0, workflow_map)

        call_tool.assert_called_once_with(
            "echo", {"value": "hello"}, "async", 60000, callback
        )


class ToolServerClientTest(unittest.TestCase):
    @patch("tool_server_client.requests.post")
    def test_completed_response_returns_result(self, post):
        response = Mock(status_code=200)
        response.json.return_value = {"status": "completed", "result": None}
        post.return_value = response

        self.assertIsNone(call_remote_tool("echo", {"value": "x"}, "wait", 500))
        post.assert_called_once_with(
            "http://tool_server:8083/api/tools/echo/calls",
            json={"arguments": {"value": "x"}, "mode": "wait", "timeout_ms": 500},
            timeout=(3, 5.5),
        )

    @patch("tool_server_client.requests.post")
    def test_accepted_response_exposes_task_id(self, post):
        response = Mock(status_code=202)
        response.json.return_value = {"task_id": "task-2"}
        post.return_value = response

        with self.assertRaises(ToolServerError) as raised:
            call_remote_tool("echo", {}, "wait", 500)

        self.assertEqual(raised.exception.task_id, "task-2")

    @patch("tool_server_client.requests.post")
    def test_async_response_returns_task_id(self, post):
        response = Mock(status_code=202)
        response.json.return_value = {"task_id": "task-3", "status": "pending"}
        post.return_value = response

        self.assertEqual(call_remote_tool("echo", {}, "async", 60000), "task-3")
        post.assert_called_once_with(
            "http://tool_server:8083/api/tools/echo/calls",
            json={"arguments": {}, "mode": "async", "timeout_ms": 60000},
            timeout=(3, 65.0),
        )

    @patch("tool_server_client.requests.post")
    def test_async_request_includes_callback(self, post):
        response = Mock(status_code=202)
        response.json.return_value = {"task_id": "task-4", "status": "pending"}
        post.return_value = response
        callback = {
            "type": "redis",
            "queue": "main_agent_queue",
            "event_type": "async_result",
            "on": ["completed", "failed"],
        }

        self.assertEqual(call_remote_tool("echo", {}, "async", 60000, callback), "task-4")
        post.assert_called_once_with(
            "http://tool_server:8083/api/tools/echo/calls",
            json={
                "arguments": {},
                "mode": "async",
                "timeout_ms": 60000,
                "callback": callback,
            },
            timeout=(3, 65.0),
        )

    @patch("tool_server_client.requests.post")
    def test_network_error_is_mapped(self, post):
        post.side_effect = requests.ConnectionError("offline")

        with self.assertRaisesRegex(ToolServerError, "remote tool request failed"):
            call_remote_tool("echo", {}, "wait", 500)


class ToolNodeValidationTest(unittest.TestCase):
    def test_legacy_tool_node_is_rejected(self):
        workflow = valid_workflow({
            "id": "legacy-tool",
            "type": "tool",
            "arguments": {"tool": "echo", "parameters": []},
        })

        with self.assertRaisesRegex(WorkflowValidationError, "unsupported node type: tool"):
            validate_workflow(workflow)

    def test_runtime_and_argument_contract_support_the_same_node_types(self):
        self.assertEqual(SUPPORTED_NODE_TYPES, set(NODE_ARGUMENT_FIELDS_BY_TYPE))
        self.assertEqual(SUPPORTED_NODE_TYPES, set(nodes_map))

    def test_remote_timeout_cannot_exceed_configured_maximum(self):
        workflow = valid_workflow({
            "id": "remote",
            "type": "remote_sync_tool",
            "arguments": {"tool": "echo", "parameters": [], "outputs": [], "timeout_ms": 10001},
        })

        with patch.dict("os.environ", {"TOOL_CLIENT_MAX_WAIT_MS": "10000"}), self.assertRaisesRegex(
            WorkflowValidationError, "must not exceed 10000"
        ):
            validate_workflow(workflow)

    def test_tool_parameter_names_may_match_other_port_ids(self):
        workflow = valid_workflow({
            "id": "remote",
            "type": "remote_sync_tool",
            "arguments": {
                "tool": "echo",
                "parameters": [
                    {"name": "output", "type": "content"},
                    {"name": "control-out", "type": "message"},
                    {"name": "content-in", "type": "list-content"},
                ],
                "outputs": [{"name": "task_id", "type": "content"}],
                "timeout_ms": 1000,
            },
        })

        validate_workflow(workflow)

    def test_remote_sync_tool_rejects_untyped_parameters(self):
        workflow = valid_workflow({
            "id": "remote",
            "type": "remote_sync_tool",
            "arguments": {"tool": "echo", "parameters": ["value"], "outputs": [], "timeout_ms": 1000},
        })

        with self.assertRaisesRegex(WorkflowValidationError, "valid name and type fields"):
            validate_workflow(workflow)

    def test_remote_tool_connections_must_match_declared_types(self):
        nodes = {
            "source": {"id": "source", "type": "construct_message"},
            "remote": {
                "id": "remote",
                "type": "remote_sync_tool",
                "arguments": {
                    "tool": "echo",
                    "parameters": [{"name": "value", "type": "message"}],
                    "outputs": [{"name": "answer", "type": "list-content"}],
                    "timeout_ms": 1000,
                },
            },
        }
        connection = {
            "fromId": "source",
            "fromPortId": "message-out",
            "toId": "remote",
            "toPortId": "value",
            "type": "message",
        }

        self.assertTrue(is_valid_connection(connection, nodes, [], []))
        self.assertFalse(is_valid_connection({**connection, "type": "content"}, nodes, [], []))

        output_connection = {
            "fromId": "remote",
            "fromPortId": "answer",
            "toId": "target",
            "toPortId": "list-in",
            "type": "list-content",
        }
        nodes["target"] = {"id": "target", "type": "foreach", "arguments": {"item_type": "content"}}
        self.assertTrue(is_valid_connection(output_connection, nodes, [], []))
        self.assertFalse(is_valid_connection({**output_connection, "type": "content"}, nodes, [], []))

    def test_legacy_remote_tool_node_is_rejected(self):
        workflow = valid_workflow({
            "id": "remote",
            "type": "remote_tool",
            "arguments": {"tool": "echo", "parameters": [], "timeout_ms": 1000},
        })

        with self.assertRaisesRegex(WorkflowValidationError, "unsupported node type: remote_tool"):
            validate_workflow(workflow)

    def test_async_timeout_is_not_limited_by_wait_maximum(self):
        workflow = valid_workflow({
            "id": "remote",
            "type": "remote_async_tool",
            "arguments": {"tool": "echo", "parameters": [], "timeout_ms": 60000},
        })

        with patch.dict("os.environ", {"TOOL_CLIENT_MAX_WAIT_MS": "10000"}):
            validate_workflow(workflow)

    def test_remote_async_tool_rejects_callback_without_statuses(self):
        workflow = valid_workflow({
            "id": "remote",
            "type": "remote_async_tool",
            "arguments": {
                "tool": "echo",
                "parameters": [],
                "timeout_ms": 60000,
                "callback": {
                    "type": "redis",
                    "queue": "main_agent_queue",
                    "event_type": "async_result",
                    "on": [],
                },
            },
        })

        with self.assertRaisesRegex(WorkflowValidationError, "valid Redis callback"):
            validate_workflow(workflow)

    def test_remote_async_tool_rejects_non_string_callback_status(self):
        workflow = valid_workflow({
            "id": "remote",
            "type": "remote_async_tool",
            "arguments": {
                "tool": "echo",
                "parameters": [],
                "timeout_ms": 60000,
                "callback": {
                    "type": "redis",
                    "queue": "main_agent_queue",
                    "event_type": "async_result",
                    "on": [{"status": "completed"}],
                },
            },
        })

        with self.assertRaisesRegex(WorkflowValidationError, "valid Redis callback"):
            validate_workflow(workflow)

    def test_control_in_is_not_a_valid_tool_parameter(self):
        workflow = valid_workflow({
            "id": "local",
            "type": "local_tool",
            "arguments": {"tool": "echo", "parameters": ["control-in"]},
        })

        with self.assertRaisesRegex(WorkflowValidationError, "other than control-in"):
            validate_workflow(workflow)


if __name__ == "__main__":
    unittest.main()