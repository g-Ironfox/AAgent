import json
import sys
import types
import unittest
from unittest.mock import Mock, patch

import requests

from tool_server_client import ToolServerError, call_remote_tool, get_remote_tool_schemas
from workflow_contract import NODE_ARGUMENT_FIELDS_BY_TYPE, SUPPORTED_NODE_TYPES, is_valid_connection
from workflow_nodes import workflow_json_tool, workflow_local_tool, workflow_remote_async_tool, workflow_remote_sync_tool
from workflow_nodes import nodes_map
from workflow_validator import WorkflowValidationError, _validate_branches_in_foreach, validate_workflow
from workflow_parser import WORKFLOW_SCHEMA_VERSION


class RemoteToolSchemaClientTest(unittest.TestCase):
    def test_fetches_only_requested_remote_tools_as_openai_functions(self):
        response = Mock()
        response.json.return_value = {"tools": [
            {"name": "provider.search", "description": "Search", "inputSchema": {"type": "object"}},
            {"name": "provider.other", "description": "Other", "inputSchema": {"type": "object"}},
        ]}
        with patch("tool_server_client.requests.get", return_value=response) as get:
            schemas = get_remote_tool_schemas({"provider.search"})

        get.assert_called_once()
        self.assertEqual(schemas, [{
            "type": "function",
            "function": {
                "name": "provider.search",
                "description": "Search",
                "parameters": {"type": "object"},
            },
        }])

    def test_missing_remote_tool_schema_fails_explicitly(self):
        response = Mock()
        response.json.return_value = {"tools": []}
        with patch("tool_server_client.requests.get", return_value=response):
            with self.assertRaisesRegex(ToolServerError, "provider.missing"):
                get_remote_tool_schemas({"provider.missing"})


def tool_workflow_map(node_type: str, **arguments) -> list[dict]:
    is_remote = node_type in {"remote_sync_tool", "remote_async_tool", "tool"}
    parameters = [{"name": "value", "type": "content"}] if is_remote else ["value"]
    output_port = (
        "task_id" if node_type == "remote_async_tool" or (node_type == "tool" and arguments.get("mode") == "async")
        else arguments.get("outputs", [{"name": "result"}])[0]["name"] if node_type == "tool"
        else "result" if node_type == "remote_sync_tool"
        else "output"
    )
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
    workflow = {
        "schema_version": WORKFLOW_SCHEMA_VERSION,
        "name": "tool_fixture",
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
    if node["type"] in {"remote_sync_tool", "remote_async_tool"}:
        parameters = node["arguments"].get("parameters", [])
        outputs = node["arguments"].get("outputs", [])
        workflow["remote_tools"] = [{
            "name": node["arguments"]["tool"],
            "input_ports": parameters if all(isinstance(port, dict) for port in parameters) else [],
            "output_ports": outputs if all(isinstance(port, dict) for port in outputs) else [],
        }]
    return workflow


class ForeachBranchValidationTest(unittest.TestCase):
    def setUp(self):
        self.nodes = {
            "loop": {"id": "loop", "type": "foreach"},
            "body": {"id": "body", "type": "json_tool"},
            "after": {"id": "after", "type": "construct_message"},
            "outside": {"id": "outside", "type": "input"},
        }
        self.connections = [
            {"fromId": "loop", "fromPortId": "loop-out", "toId": "body", "toPortId": "control-in", "type": "control"},
            {"fromId": "body", "fromPortId": "control-out", "toId": "loop", "toPortId": "loop-in", "type": "control"},
            {"fromId": "loop", "fromPortId": "control-out", "toId": "after", "toPortId": "control-in", "type": "control"},
        ]

    def test_rejects_connected_json_tool_error_branch_inside_loop(self):
        self.connections.append({
            "fromId": "body", "fromPortId": "error-out", "toId": "after", "toPortId": "control-in", "type": "control",
        })
        with self.assertRaisesRegex(WorkflowValidationError, "branching control flow.*body"):
            _validate_branches_in_foreach(self.nodes, self.connections)

    def test_allows_single_path_loop_and_branch_after_loop(self):
        self.nodes["router"] = {"id": "router", "type": "router"}
        self.nodes["branch_a"] = {"id": "branch_a", "type": "output"}
        self.nodes["branch_b"] = {"id": "branch_b", "type": "output"}
        self.connections.extend([
            {"fromId": "after", "fromPortId": "control-out", "toId": "router", "toPortId": "control-in", "type": "control"},
            {"fromId": "router", "fromPortId": "a", "toId": "branch_a", "toPortId": "control-in", "type": "control"},
            {"fromId": "router", "fromPortId": "branch$others", "toId": "branch_b", "toPortId": "control-in", "type": "control"},
        ])
        _validate_branches_in_foreach(self.nodes, self.connections)

    def test_rejects_body_node_with_external_control_entry(self):
        self.connections.append({
            "fromId": "outside", "fromPortId": "control-out", "toId": "body", "toPortId": "control-in", "type": "control",
        })
        with self.assertRaisesRegex(WorkflowValidationError, "entry from outside.*body"):
            _validate_branches_in_foreach(self.nodes, self.connections)


class ToolNodeExecutionTest(unittest.TestCase):
    def test_validator_accepts_json_tool_without_static_tool_metadata(self):
        self.assertIn("json_tool", SUPPORTED_NODE_TYPES)
        self.assertEqual(NODE_ARGUMENT_FIELDS_BY_TYPE["json_tool"], set())
        validate_workflow(valid_workflow({"id": "dynamic", "type": "json_tool"}))

    def test_json_tool_dispatches_to_registered_local_tool(self):
        node = {"id": "json-node", "type": "json_tool", "data_inputs": {
            "tool-name": [None, None, "local_echo"], "arguments-json": [None, None, '{"value":3}'],
        }, "data_outputs": {"result-json": [[1, "result"]]}, "successors": {"next": 1}}
        target = {"id": "target", "data_inputs": {"result": [0, "result-json", None]}, "data_outputs": {}}
        execute_tool = Mock(return_value={"answer": 3})
        tools_module = types.ModuleType("tools.tool")
        tools_module.execute_tool = execute_tool
        tools_module.tool_handlers = {"local_echo": object()}
        with patch.dict(sys.modules, {"tools.tool": tools_module}), patch("tool_server_client.call_remote_tool") as remote:
            self.assertEqual(workflow_json_tool(0, [node, target]), 1)
        execute_tool.assert_called_once_with("json-node", "local_echo", {"value": 3}, preserve_result=True)
        remote.assert_not_called()
        self.assertEqual(target["data_inputs"]["result"][2], '{"answer":3}')

    @patch("tool_server_client.call_remote_tool", return_value={"ok": True})
    def test_json_tool_dispatches_to_remote_when_not_locally_registered(self, call_tool):
        node = {"id": "json-node", "type": "json_tool", "data_inputs": {
            "tool-name": [None, None, "remote_echo"], "arguments-json": [None, None, "{}"],
        }, "data_outputs": {"result-json": [[1, "result"]]}, "successors": {"next": 1}}
        target = {"id": "target", "data_inputs": {"result": [0, "result-json", None]}, "data_outputs": {}}
        tools_module = types.ModuleType("tools.tool")
        tools_module.execute_tool = Mock()
        tools_module.tool_handlers = {}
        with patch.dict(sys.modules, {"tools.tool": tools_module}), patch.dict(
            "os.environ", {"TOOL_CLIENT_DEFAULT_WAIT_MS": "23000"}
        ):
            self.assertEqual(workflow_json_tool(0, [node, target]), 1)
        call_tool.assert_called_once_with("remote_echo", {}, "wait", 23000, None)
        self.assertEqual(target["data_inputs"]["result"][2], '{"ok":true}')

    def test_json_tool_routes_unknown_tool_to_error_without_submitting_task(self):
        node = {"id": "json-node", "type": "json_tool", "data_inputs": {
            "tool-name": [None, None, "missing.tool"], "arguments-json": [None, None, "{}"],
        }, "data_outputs": {"result-json": [[1, "result"]], "error-json": [[1, "error"]]},
            "successors": {"next": 2, "error": 1}}
        target = {"data_inputs": {"result": [0, "result-json", None], "error": [0, "error-json", None]}}
        tools_module = types.ModuleType("tools.tool")
        tools_module.execute_tool = Mock()
        tools_module.tool_handlers = {}
        response = Mock()
        response.json.return_value = {"tools": []}
        with patch.dict(sys.modules, {"tools.tool": tools_module}), \
             patch("tool_server_client.requests.get", return_value=response), \
             patch("tool_server_client.requests.post") as post:
            self.assertEqual(workflow_json_tool(0, [node, target]), 1)
        error = json.loads(target["data_inputs"]["error"][2])
        self.assertEqual(error["tool"], "missing.tool")
        self.assertEqual(error["error"]["type"], "ToolServerError")
        self.assertIn("missing.tool", error["error"]["message"])
        self.assertIsNone(target["data_inputs"]["result"][2])
        post.assert_not_called()
        tools_module.execute_tool.assert_not_called()

    def test_unified_local_tool_dispatches_from_metadata_kind(self):
        workflow_map = tool_workflow_map("tool", mode="sync", outputs=[{"name": "output", "type": "content"}])
        workflow_map[0]["_tool_kind"] = "local"
        fake_tools = types.ModuleType("tools.tool")
        fake_tools.execute_tool = Mock(return_value={"ok": True})
        with patch.dict(sys.modules, {"tools.tool": fake_tools}):
            self.assertEqual(nodes_map["tool"](0, workflow_map), 1)
        fake_tools.execute_tool.assert_called_once_with("tool-node", "echo", {"value": "hello"}, preserve_result=True)
        self.assertEqual(workflow_map[1]["data_inputs"]["result"][2], '{"ok": true}')

    def test_unified_local_tool_distributes_named_outputs(self):
        outputs = [
            {"name": "details", "type": "map-content"},
            {"name": "message", "type": "content"},
        ]
        workflow_map = tool_workflow_map("tool", mode="sync", outputs=outputs)
        workflow_map[0]["_tool_kind"] = "local"
        workflow_map[0]["data_outputs"] = {"details": [[1, "details"]], "message": [[1, "message"]]}
        workflow_map[1]["data_inputs"] = {"details": [0, "details", None], "message": [0, "message", None]}
        fake_tools = types.ModuleType("tools.tool")
        fake_tools.execute_tool = Mock(return_value={"details": {"key": "value"}, "message": "done"})
        with patch.dict(sys.modules, {"tools.tool": fake_tools}):
            self.assertEqual(nodes_map["tool"](0, workflow_map), 1)
        self.assertEqual(workflow_map[1]["data_inputs"]["details"][2], {"key": "value"})
        self.assertEqual(workflow_map[1]["data_inputs"]["message"][2], "done")
        fake_tools.execute_tool.assert_called_once_with("tool-node", "echo", {"value": "hello"}, preserve_result=True)

    @patch("tool_server_client.call_remote_tool", return_value="remote-result")
    def test_unified_remote_tool_dispatches_to_remote_client(self, call_tool):
        workflow_map = tool_workflow_map("tool", mode="sync", outputs=[{"name": "result", "type": "content"}])
        workflow_map[0]["_tool_kind"] = "remote"
        self.assertEqual(nodes_map["tool"](0, workflow_map), 1)
        call_tool.assert_called_once_with("echo", {"value": "hello"}, "wait", 10000, None)
        self.assertEqual(workflow_map[1]["data_inputs"]["result"][2], "remote-result")

    @patch("tool_server_client.call_remote_tool")
    def test_sync_tool_cannot_dispatch_async_even_without_validation(self, call_tool):
        workflow_map = tool_workflow_map("tool", mode="async", outputs=[])
        workflow_map[0]["_tool_kind"] = "remote"
        with self.assertRaisesRegex(ValueError, "only supports sync"):
            nodes_map["tool"](0, workflow_map)
        call_tool.assert_not_called()

    def test_local_tool_serializes_result(self):
        execute_tool = Mock()
        execute_tool.return_value = {"ok": True}
        tool_module = types.ModuleType("tools.tool")
        tool_module.execute_tool = execute_tool
        workflow_map = tool_workflow_map("local_tool")

        with patch.dict(sys.modules, {"tools.tool": tool_module}):
            next_id = workflow_local_tool(0, workflow_map)

        self.assertEqual(next_id, 1)
        execute_tool.assert_called_once_with("tool-node", "echo", {"value": "hello"}, preserve_result=True)
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
            "queue": "tool_result_callbacks",
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
    def setUp(self):
        response = Mock()
        response.json.return_value = {"tools": [{"name": "echo"}]}
        self.get = self.enterContext(patch("tool_server_client.requests.get", return_value=response))

    @patch("tool_server_client.requests.post")
    def test_missing_tool_is_rejected_before_submitting_sync_or_async_task(self, post):
        self.get.return_value.json.return_value = {"tools": []}
        for mode in ("wait", "async"):
            with self.subTest(mode=mode):
                with self.assertRaisesRegex(ToolServerError, "echo"):
                    call_remote_tool("echo", {}, mode, 500)
        post.assert_not_called()

    @patch("tool_server_client.requests.post")
    def test_registry_failure_prevents_task_submission(self, post):
        self.get.side_effect = requests.ConnectionError("offline")
        with self.assertRaisesRegex(ToolServerError, "remote tool schema request failed"):
            call_remote_tool("echo", {}, "wait", 500)
        post.assert_not_called()

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

        self.get.assert_called_once_with("http://tool_server:8083/api/tools", timeout=(3, 10))

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
            "queue": "tool_result_callbacks",
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
    def test_unified_tool_requires_metadata_declaration(self):
        workflow = valid_workflow({
            "id": "undeclared-tool",
            "type": "tool",
            "arguments": {"tool": "echo", "parameters": [], "outputs": []},
        })

        with self.assertRaisesRegex(WorkflowValidationError, "metadata.tools"):
            validate_workflow(workflow)

    def test_validator_accepts_unified_local_tool_metadata(self):
        node = {"id": "tool", "type": "tool", "arguments": {
            "tool": "echo", "parameters": [{"name": "value", "type": "content"}],
            "outputs": [{"name": "output", "type": "content"}], "mode": "sync",
        }}
        workflow = valid_workflow(node)
        workflow["metadata"] = {"structs": [], "tools": [{
            "name": "echo", "kind": "local", "input_ports": [{"name": "value", "type": "content"}],
            "output_ports": [{"name": "output", "type": "content"}],
        }]}
        validate_workflow(workflow)

    def test_validator_accepts_named_local_tool_outputs(self):
        outputs = [
            {"name": "details", "type": "map-content"},
            {"name": "message", "type": "content"},
        ]
        node = {"id": "tool", "type": "tool", "arguments": {
            "tool": "echo", "parameters": [{"name": "value", "type": "content"}],
            "outputs": outputs, "mode": "sync",
        }}
        workflow = valid_workflow(node)
        workflow["metadata"] = {"structs": [], "tools": [{
            "name": "echo", "kind": "local", "input_ports": [{"name": "value", "type": "content"}],
            "output_ports": outputs,
        }]}
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
                    {"name": "control-out", "type": "number"},
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

    def test_remote_tool_ports_must_match_metadata_contract(self):
        workflow = valid_workflow({
            "id": "remote",
            "type": "remote_sync_tool",
            "arguments": {
                "tool": "echo",
                "parameters": [{"name": "value", "type": "content"}],
                "outputs": [{"name": "result", "type": "content"}],
                "timeout_ms": 1000,
            },
        })
        workflow["remote_tools"][0]["input_ports"] = [{"name": "query", "type": "content"}]

        with self.assertRaisesRegex(WorkflowValidationError, "inputs must match"):
            validate_workflow(workflow)

    def test_remote_tool_connections_must_match_declared_types(self):
        nodes = {
            "source": {"id": "source", "type": "construct_message"},
            "remote": {
                "id": "remote",
                "type": "remote_sync_tool",
                "arguments": {
                    "tool": "echo",
                    "parameters": [{"name": "value", "type": "content"}],
                    "outputs": [{"name": "answer", "type": "list-content"}],
                    "timeout_ms": 1000,
                },
            },
        }
        connection = {
            "fromId": "source",
            "fromPortId": "content-out",
            "toId": "remote",
            "toPortId": "value",
            "type": "content",
        }

        self.assertTrue(is_valid_connection(connection, nodes, [], []))
        self.assertFalse(is_valid_connection({**connection, "type": "number"}, nodes, [], []))

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

        with self.assertRaisesRegex(WorkflowValidationError, "nodes.1.type"):
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
                    "queue": "tool_result_callbacks",
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
                    "queue": "tool_result_callbacks",
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
