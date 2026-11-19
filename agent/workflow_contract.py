"""Define workflow node types and their control/data ports."""

from __future__ import annotations

import math
from typing import Any


DATA_CONNECTION_TYPES = {
    "content",
    "number",
    "message",
    "list-content",
    "list-message",
    "map-content",
}
SUPPORTED_NODE_TYPES = {
    "input",
    "output",
    "function_input",
    "function_output",
    "function_call",
    "router",
    "construct_message",
    "construct_content",
    "construct_map_content",
    "construct_struct",
    "struct_get",
    "struct_update",
    "struct_to_json",
    "json_to_struct",
    "map_content_get",
    "output_to_terminal",
    "wait_terminal_event",
    "read_terminal_input",
    "deserialize_json",
    "construct_list",
    "list_append",
    "list_length",
    "list_get",
    "list_slice",
    "foreach",
    "while_pop",
    "llm",
    "tool",
    "json_tool",
    "local_tool",
    "remote_sync_tool",
    "remote_async_tool",
    "context_create",
    "context_read",
    "context_write",
    "session_create",
    "session_read",
    "session_write",
    "spawn_and_wait_subprocess",
}

NODE_BASE_FIELDS = {"id", "type", "name", "x", "y", "arguments", "function_id"}
NODE_SHARED_FIELDS = {
    "workflowPorts",
    "dataInputPorts",
    "input_ports",
    "output_ports",
    "function_ports",
}
NODE_ARGUMENT_FIELDS_BY_TYPE = {
    "input": set(),
    "output": set(),
    "function_input": set(),
    "function_output": set(),
    "function_call": {"function_id"},
    "router": {"branches"},
    "construct_message": {"role", "role_source"},
    "construct_content": {"append_items"},
    "construct_map_content": {"mappings"},
    "construct_struct": {"struct_id"},
    "struct_get": {"struct_id", "field", "missing", "has_fallback"},
    "struct_update": {"struct_id", "updates", "remove_fields"},
    "struct_to_json": {"value_type"},
    "json_to_struct": {"value_type"},
    "map_content_get": set(),
    "output_to_terminal": set(),
    "wait_terminal_event": set(),
    "read_terminal_input": set(),
    "deserialize_json": {"outputs"},
    "construct_list": {"item_type", "initial_value_count"},
    "list_append": {"item_type", "position"},
    "list_length": {"value_type"},
    "list_get": {"value_type", "index_source", "index"},
    "list_slice": {"value_type", "start_source", "start", "stop_source", "stop", "step_source", "step"},
    "foreach": {"item_type"},
    "while_pop": {"value_type", "position", "context_id_source", "context_id"},
    "llm": {"model", "think", "tool_calls", "tools"},
    "tool": {"tool", "parameters", "outputs", "mode", "timeout_ms", "callback"},
    "json_tool": set(),
    "local_tool": {"tool", "parameters"},
    "remote_sync_tool": {"tool", "parameters", "outputs", "timeout_ms"},
    "remote_async_tool": {"tool", "parameters", "timeout_ms", "callback"},
    "context_create": {"value_type", "context_id"},
    "context_read": {"value_type", "context_id_source", "context_id"},
    "context_write": {"value_type", "context_id_source", "context_id"},
    "session_create": {"value_type"},
    "session_read": {"value_type"},
    "session_write": {"value_type"},
    "spawn_and_wait_subprocess": {"workflow_file"},
}
NODE_ARGUMENT_FIELDS = set().union(*NODE_ARGUMENT_FIELDS_BY_TYPE.values())


def is_number_value(value: Any) -> bool:
    """Accept JSON integers and finite floats, excluding booleans."""
    return (isinstance(value, int) and not isinstance(value, bool)) or (
        isinstance(value, float) and math.isfinite(value)
    )


def node_arguments(node: dict[str, Any]) -> dict[str, Any]:
    arguments = node.get("arguments")
    return arguments if isinstance(arguments, dict) else {}


def node_argument(node: dict[str, Any], name: str, default: Any = None) -> Any:
    return node_arguments(node).get(name, default)


def list_type_for_item(item_type: Any) -> str:
    return f"list-{item_type}"


def tool_parameter_names(node: dict[str, Any]) -> list[str]:
    parameters = node_argument(node, "parameters", [])
    if node.get("type") in {"remote_sync_tool", "remote_async_tool", "tool"}:
        return [parameter["name"] for parameter in parameters]
    return parameters


def tool_parameter_type(node: dict[str, Any], name: str) -> str | None:
    if node.get("type") == "json_tool":
        return "content" if name in {"tool-name", "arguments-json"} else None
    if node.get("type") == "local_tool":
        return "content" if name in tool_parameter_names(node) else None
    if node.get("type") in {"remote_sync_tool", "remote_async_tool", "tool"}:
        return next(
            (parameter["type"] for parameter in node_argument(node, "parameters", []) if parameter["name"] == name),
            None,
        )
    return None


def tool_output_type(node: dict[str, Any], name: str) -> str | None:
    if node.get("type") == "json_tool":
        return "content" if name in {"result-json", "error-json"} else None
    if node.get("type") == "tool":
        return next(
            (output["type"] for output in node_argument(node, "outputs", []) if output["name"] == name),
            None,
        )
    if node.get("type") == "local_tool":
        return "content" if name == "output" else None
    if node.get("type") == "remote_sync_tool":
        return next(
            (output["type"] for output in node_argument(node, "outputs", []) if output["name"] == name),
            None,
        )
    if node.get("type") == "remote_async_tool" and name == "task_id":
        return "content"
    return None


def normalize_node_arguments(node: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in node.items()
        if key in NODE_BASE_FIELDS or key in NODE_SHARED_FIELDS
    }


def boundary_ports(
    ports: list[dict[str, Any]],
) -> list[dict[str, str]]:
    return [
        {
            "id": f"workflow:{port['name']}",
            "name": port["name"],
            "type": port["type"],
        }
        for port in ports
    ]


def data_ports_for_node(
    node: dict[str, Any],
    input_ports: list[dict[str, Any]],
    output_ports: list[dict[str, Any]],
) -> tuple[set[str], set[str]]:
    node_type = node["type"]
    declared_inputs = set(node.get("dataInputPorts", []))
    if node_type == "input":
        return declared_inputs, {
            port["id"] for port in boundary_ports(input_ports)
        }
    if node_type == "output":
        return declared_inputs | {
            port["id"] for port in boundary_ports(output_ports)
        }, set()
    if node_type == "function_input":
        return declared_inputs, {f"function:{port['name']}" for port in node.get("function_ports", [])}
    if node_type == "function_output":
        return declared_inputs | {f"function:{port['name']}" for port in node.get("function_ports", [])}, set()
    if node_type == "function_call":
        return (
            {f"function:{port['name']}" for port in node.get("input_ports", [])},
            {f"function:{port['name']}" for port in node.get("output_ports", [])},
        )
    if node_type == "router":
        return declared_inputs | {"content-in"}, set()
    if node_type == "llm":
        outputs = {"output"}
        if node_argument(node, "think") is True:
            outputs.add("reasoning")
        if node_argument(node, "tool_calls") is True:
            outputs.add("tool_calls")
        inputs = {"messages-in"}
        if node_argument(node, "tool_calls") is True:
            inputs.add("available-tools-in")
        return inputs, outputs
    if node_type == "construct_message":
        inputs = declared_inputs | {"content-in"}
        if node_argument(node, "role_source", "fixed") == "port":
            inputs.add("role-in")
        return inputs, {"message-out"}
    if node_type == "construct_content":
        return declared_inputs, {"content-out"}
    if node_type == "construct_map_content":
        return declared_inputs, {"map-out"}
    if node_type == "construct_struct":
        return declared_inputs, {"struct-out"}
    if node_type == "struct_get":
        inputs = declared_inputs | {"struct-in"}
        if node_argument(node, "has_fallback"):
            inputs.add("fallback-in")
        return inputs, {"value-out"}
    if node_type == "struct_update":
        return declared_inputs | {"struct-in"}, {"struct-out"}
    if node_type in {"struct_to_json", "json_to_struct"}:
        return declared_inputs | ({"value-in"} if node_type == "struct_to_json" else {"content-in"}), {"content-out" if node_type == "struct_to_json" else "value-out"}
    if node_type == "map_content_get":
        return declared_inputs | {"map-in", "key-in"}, {"content-out"}
    if node_type == "read_terminal_input":
        return set(), {"list-out"}
    if node_type == "wait_terminal_event":
        return set(), set()
    if node_type == "output_to_terminal":
        return declared_inputs | {"content-in"}, set()
    if node_type == "deserialize_json":
        return {"content-in"}, {
            output["key"] for output in node_argument(node, "outputs", [])
        }
    if node_type == "construct_list":
        return declared_inputs, {"list-out"}
    if node_type == "list_get":
        inputs = {"list-in"} if node_argument(node, "index_source", "port") == "fixed" else {"list-in", "index-in"}
        return inputs, {"item-out"}
    if node_type == "list_length":
        return {"list-in"}, {"length-out"}
    if node_type == "list_slice":
        return {"list-in"} | {
            f"{name}-in" for name in ("start", "stop", "step")
            if node_argument(node, f"{name}_source", "port") != "fixed"
        }, {"list-out"}
    if node_type == "list_append":
        return declared_inputs | {"list-in", "item-in"}, {"list-out"}
    if node_type == "foreach":
        return declared_inputs | {"list-in"}, {"item-out"}
    if node_type == "while_pop":
        id_inputs = {"context-id"} if node_argument(node, "context_id_source", "port") == "port" else set()
        return id_inputs, {"item-out"}
    if node_type == "tool":
        outputs = {output["name"] for output in node_argument(node, "outputs", [])}
        return declared_inputs | set(tool_parameter_names(node)), outputs
    if node_type == "json_tool":
        return declared_inputs | {"tool-name", "arguments-json"}, {"result-json", "error-json"}
    if node_type == "local_tool":
        return declared_inputs | set(tool_parameter_names(node)), {"output"}
    if node_type == "remote_sync_tool":
        return declared_inputs | set(tool_parameter_names(node)), {
            output["name"] for output in node_argument(node, "outputs", [])
        }
    if node_type == "remote_async_tool":
        return declared_inputs | set(tool_parameter_names(node)), {"task_id"}
    if node_type in {"context_create", "session_create"}:
        return {"initial-value"}, {"context-id" if node_type == "context_create" else "session-id"}
    if node_type in {"context_read", "session_read"}:
        input_ports = {"context-id"} if node_type == "context_read" and node_argument(node, "context_id_source", "port") == "port" else ({"session-id"} if node_type == "session_read" else set())
        return input_ports, {"value-out"}
    if node_type in {"context_write", "session_write"}:
        id_port = "context-id" if node_type == "context_write" else "session-id"
        id_inputs = {id_port} if node_type == "session_write" or node_argument(node, "context_id_source", "port") == "port" else set()
        return id_inputs | {"value-in"}, {id_port, "value-out"}
    if node_type == "spawn_and_wait_subprocess":
        return (
            {f"workflow:{port['name']}" for port in node.get("input_ports", [])},
            {f"workflow:{port['name']}" for port in node.get("output_ports", [])},
        )
    return declared_inputs, set()


def data_type_for_port(
    node: dict[str, Any], port_id: str, struct_definitions: dict[str, Any] | None = None
) -> str | None:
    definitions = struct_definitions or {}
    kind = node.get("type")
    if kind in {"function_input", "function_output"}:
        return next((port["type"] for port in node.get("function_ports", []) if f"function:{port['name']}" == port_id), None)
    value_type = node_argument(node, "value_type")
    if kind == "construct_struct":
        sid = node_argument(node, "struct_id")
        if port_id == "struct-out": return f"struct:{sid}"
        return next((f["type"] for f in definitions.get(sid, {}).get("fields", []) if f["name"] == port_id), None)
    if kind == "struct_get":
        sid = node_argument(node, "struct_id")
        field_type = next((f["type"] for f in definitions.get(sid, {}).get("fields", []) if f["name"] == node_argument(node, "field")), None)
        if port_id == "struct-in": return f"struct:{sid}"
        if port_id in {"fallback-in", "value-out"}: return field_type
    if kind == "struct_update":
        sid = node_argument(node, "struct_id")
        if port_id in {"struct-in", "struct-out"}: return f"struct:{sid}"
        return next((f["type"] for f in definitions.get(sid, {}).get("fields", []) if f["name"] == port_id), None)
    if kind == "struct_to_json":
        return value_type if port_id == "value-in" else ("content" if port_id == "content-out" else None)
    if kind == "json_to_struct":
        return "content" if port_id == "content-in" else (value_type if port_id == "value-out" else None)
    if kind == "read_terminal_input":
        return "list-content" if port_id == "list-out" else None
    if kind == "construct_list":
        return f"list-{node_argument(node, 'item_type')}" if port_id == "list-out" else node_argument(node, "item_type")
    if kind == "list_get":
        if port_id == "list-in": return value_type
        if port_id == "index-in": return "number" if node_argument(node, "index_source", "port") != "fixed" else None
        if port_id == "item-out": return value_type.removeprefix("list-")
        return None
    if kind == "list_length":
        return value_type if port_id == "list-in" else ("number" if port_id == "length-out" else None)
    if kind == "list_slice":
        if port_id in {"list-in", "list-out"}: return value_type
        for name in ("start", "stop", "step"):
            if port_id == f"{name}-in" and node_argument(node, f"{name}_source", "port") != "fixed":
                return "number"
        return None
    if kind == "list_append":
        if port_id in {"list-in", "list-out"}: return f"list-{node_argument(node, 'item_type')}"
        return node_argument(node, "item_type") if port_id == "item-in" else None
    if kind == "foreach":
        return f"list-{node_argument(node, 'item_type')}" if port_id == "list-in" else (node_argument(node, "item_type") if port_id == "item-out" else None)
    if kind == "while_pop":
        if port_id == "context-id": return "content"
        if port_id == "item-out": return value_type.removeprefix("list-")
    if kind in {"context_create", "context_read", "context_write"}:
        if port_id in {"initial-value", "value-in", "value-out"}: return value_type
        if port_id == "context-id": return "content"
    return None


def control_ports_for_node(node: dict[str, Any]) -> tuple[set[str], set[str]]:
    node_type = node["type"]
    if node_type in {"input", "function_input"}:
        return set(), {"control-out"}
    if node_type in {"output", "function_output"}:
        return {"control-in"}, set()
    if node_type == "router":
        return {"control-in"}, {
            branch["id"] for branch in node_argument(node, "branches", [])
        } | {"branch$others"}
    if node_type == "json_tool":
        return {"control-in"}, {"control-out", "error-out"}
    if node_type in {"foreach", "while_pop"}:
        return {"control-in", "loop-in"}, {"control-out", "loop-out"}
    return {"control-in"}, {"control-out"}


def connection_validation_error(
    connection: Any,
    nodes_by_id: dict[str, dict[str, Any]],
    input_ports: list[dict[str, Any]],
    output_ports: list[dict[str, Any]],
    struct_definitions: dict[str, Any] | None = None,
) -> str | None:
    if not isinstance(connection, dict):
        return "connection must be an object"
    from_id = connection.get("fromId")
    to_id = connection.get("toId")
    from_port = connection.get("fromPortId")
    to_port = connection.get("toPortId")
    connection_type = connection.get("type")
    if not all(isinstance(value, str) and value for value in (from_id, to_id, from_port, to_port)):
        return "connection endpoints must be non-empty strings"
    source_node = nodes_by_id.get(from_id)
    target_node = nodes_by_id.get(to_id)
    if source_node is None or target_node is None:
        return "connection references an unknown node"
    try:
        if connection_type == "control":
            source_inputs, source_outputs = control_ports_for_node(source_node)
            target_inputs, target_outputs = control_ports_for_node(target_node)
            if from_port not in source_outputs:
                return f"invalid control output: {from_port}"
            if to_port not in target_inputs:
                return f"invalid control input: {to_port}"
            return None
        if connection_type not in DATA_CONNECTION_TYPES and not connection_type.startswith(("struct:", "list-struct:")):
            return "connection type is unsupported"
        _, source_outputs = data_ports_for_node(source_node, input_ports, output_ports)
        target_inputs, _ = data_ports_for_node(target_node, input_ports, output_ports)
        if from_port not in source_outputs or to_port not in target_inputs:
            return "unknown data port"
        source_expected = data_type_for_port(source_node, from_port, struct_definitions)
        target_expected = data_type_for_port(target_node, to_port, struct_definitions)
        if source_node["type"] == "function_call":
            source_expected = next(p["type"] for p in source_node["output_ports"] if f"function:{p['name']}" == from_port)
        if target_node["type"] == "function_call":
            target_expected = next(p["type"] for p in target_node["input_ports"] if f"function:{p['name']}" == to_port)
        if source_expected is not None and connection_type != source_expected:
            return f"source port {from_port} requires {source_expected} data"
        if target_expected is not None and connection_type != target_expected:
            return f"target port {to_port} requires {target_expected} data"
        if connection_type.startswith(("struct:", "list-struct:")):
            ref = connection_type.split(":", 1)[1]
            if struct_definitions is None or ref not in struct_definitions:
                return "Struct type is not declared in this Workflow"
        if source_node["type"] == "input":
            source_port = next(port for port in boundary_ports(input_ports) if port["id"] == from_port)
            if connection_type != source_port["type"]:
                return f"workflow input port {from_port} requires {source_port['type']} data"
        if target_node["type"] == "output":
            target_port = next(port for port in boundary_ports(output_ports) if port["id"] == to_port)
            if connection_type != target_port["type"]:
                return f"workflow output port {to_port} requires {target_port['type']} data"
        if source_node["type"] == "spawn_and_wait_subprocess":
            source_port = next(port for port in source_node.get("output_ports", []) if f"workflow:{port['name']}" == from_port)
            if connection_type != source_port["type"]:
                return f"subprocess Workflow file output {from_port} requires {source_port['type']} data"
        if target_node["type"] == "spawn_and_wait_subprocess":
            target_port = next(port for port in target_node.get("input_ports", []) if f"workflow:{port['name']}" == to_port)
            if connection_type != target_port["type"]:
                return f"subprocess Workflow file input {to_port} requires {target_port['type']} data"
        if target_node["type"] in {"tool", "local_tool", "remote_sync_tool", "remote_async_tool", "json_tool"} and connection_type != tool_parameter_type(target_node, to_port):
            return f"tool input {to_port} requires {tool_parameter_type(target_node, to_port)} data"
        if source_node["type"] in {"tool", "local_tool", "remote_sync_tool", "remote_async_tool", "json_tool"} and connection_type != tool_output_type(source_node, from_port):
            return f"tool output {from_port} requires {tool_output_type(source_node, from_port)} data"
        if target_node["type"] in {"context_create", "context_write", "session_create", "session_write"}:
            value_port = "initial-value" if target_node["type"].endswith("create") else "value-in"
            expected_type = node_argument(target_node, "value_type") if to_port == value_port else "content"
            if connection_type != expected_type:
                return f"context/session input {to_port} requires {expected_type} data"
        if target_node["type"] in {"context_read", "session_read"} and connection_type != "content":
            return f"{target_node['type']} output requires content data"
        if source_node["type"] in {"context_create", "session_create"} and connection_type != "content":
            return f"{source_node['type']} output requires content data"
        if source_node["type"] in {"context_read", "context_write", "session_read", "session_write"}:
            expected_type = "content" if from_port in {"context-id", "session-id"} else node_argument(source_node, "value_type")
            if connection_type != expected_type:
                return f"context/session output {from_port} requires {expected_type} data"
        if target_node["type"] == "output_to_terminal" and connection_type != "content":
            return "output_to_terminal content-in requires content data"
        if target_node["type"] == "deserialize_json" and (
            to_port != "content-in" or connection_type != "content"
        ):
            return "deserialize_json content-in requires content data"
        if target_node["type"] == "map_content_get":
            expected_type = "map-content" if to_port == "map-in" else "content"
            if to_port not in {"map-in", "key-in"} or connection_type != expected_type:
                return f"map_content_get {to_port} requires {expected_type} data"
        if target_node["type"] == "construct_map_content" and connection_type != "content":
            return "construct_map_content value input requires content data"
        if source_node["type"] == "construct_map_content" and (
            from_port != "map-out" or connection_type != "map-content"
        ):
            return "construct_map_content map-out requires map-content data"
        if source_node["type"] == "map_content_get" and (
            from_port != "content-out" or connection_type != "content"
        ):
            return "map_content_get content-out requires content data"
        if source_node["type"] == "deserialize_json":
            output_type = next(
                (
                    output["type"]
                    for output in node_argument(source_node, "outputs", [])
                    if output["key"] == from_port
                ),
                None,
            )
            if connection_type != output_type:
                return f"deserialize_json output {from_port} requires {output_type} data"
        source_type = source_node["type"]
        target_type = target_node["type"]
        if target_type == "llm":
            expected_type = "list-message" if to_port == "messages-in" else "list-content"
            if connection_type != expected_type:
                return f"llm {to_port} input requires {expected_type} data"
        if target_type == "construct_message" and connection_type != "content":
            return f"construct_message {to_port} requires content data"
        if source_type == "construct_message" and connection_type != "message":
            return "construct_message message-out requires message data"
        if target_type == "construct_list" and connection_type != node_argument(target_node, "item_type"):
            return f"construct_list input requires {node_argument(target_node, 'item_type')} data"
        if source_type == "construct_list" and connection_type != list_type_for_item(node_argument(source_node, "item_type")):
            return f"construct_list output requires {list_type_for_item(node_argument(source_node, 'item_type'))} data"
        if target_type == "list_append":
            expected_type = (
                list_type_for_item(node_argument(target_node, "item_type"))
                if to_port == "list-in"
                else node_argument(target_node, "item_type")
            )
            if connection_type != expected_type:
                return f"list_append {to_port} requires {expected_type} data"
        if source_type == "list_append" and connection_type != list_type_for_item(node_argument(source_node, "item_type")):
            return f"list_append output requires {list_type_for_item(node_argument(source_node, 'item_type'))} data"
        if target_type == "foreach" and (connection_type != list_type_for_item(node_argument(target_node, "item_type")) or to_port != "list-in"):
            return f"foreach input requires {list_type_for_item(node_argument(target_node, 'item_type'))} data"
        if source_type == "foreach" and (connection_type != node_argument(source_node, "item_type") or from_port != "item-out"):
            return f"foreach output requires {node_argument(source_node, 'item_type')} data"
        if source_type == "llm" and from_port == "tool_calls" and connection_type != "list-content":
            return "llm tool_calls output requires list-content data"
        return None
    except (KeyError, StopIteration, TypeError):
        return "connection does not match the node contract"


def is_valid_connection(
    connection: Any,
    nodes_by_id: dict[str, dict[str, Any]],
    input_ports: list[dict[str, Any]],
    output_ports: list[dict[str, Any]],
) -> bool:
    return connection_validation_error(
        connection, nodes_by_id, input_ports, output_ports
    ) is None


def filter_connections(
    connections: list[Any],
    nodes: list[dict[str, Any]],
    input_ports: list[dict[str, Any]],
    output_ports: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    nodes_by_id = {node.get("id"): node for node in nodes if isinstance(node, dict)}
    return [
        connection
        for connection in connections
        if is_valid_connection(connection, nodes_by_id, input_ports, output_ports)
    ]


def migrate_subprocess_workflow_format(workflow: dict[str, Any]) -> dict[str, Any]:
    """Normalize legacy fields without mutation; Workflow identity comes from its file."""
    from copy import deepcopy

    migrated = deepcopy(workflow)
    migrated.pop("name", None)
    if isinstance(migrated.get("metadata"), dict):
        migrated["metadata"].pop("name", None)
    if "workflow_nodes" in migrated:
        old = migrated.pop("workflow_nodes")
        if "subprocess_workflow_files" in migrated and migrated["subprocess_workflow_files"] != old:
            raise ValueError("conflicting workflow_nodes and subprocess_workflow_files")
        migrated["subprocess_workflow_files"] = old
    references = migrated.get("subprocess_workflow_files", [])
    for reference in references if isinstance(references, list) else []:
        if not isinstance(reference, dict) or "workflow_name" not in reference:
            continue
        old = reference.pop("workflow_name")
        if "name" in reference and reference["name"] != old:
            raise ValueError("conflicting subprocess file names")
        reference["name"] = old
    nodes = migrated.get("nodes", [])
    for node in nodes if isinstance(nodes, list) else []:
        if not isinstance(node, dict) or node.get("type") not in {"workflow", "spawn_and_wait_subprocess"}:
            continue
        node["type"] = "spawn_and_wait_subprocess"
        for arguments in (node, node.get("arguments")):
            if not isinstance(arguments, dict) or "workflow_name" not in arguments:
                continue
            old = arguments.pop("workflow_name")
            if "workflow_file" in arguments and arguments["workflow_file"] != old:
                raise ValueError("conflicting workflow_name and workflow_file")
            arguments["workflow_file"] = old
    return migrated
