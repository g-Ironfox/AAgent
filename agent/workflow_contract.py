"""Define workflow node types and their control/data ports."""

from __future__ import annotations

from typing import Any


DATA_CONNECTION_TYPES = {
    "content",
    "message",
    "event",
    "list-content",
    "list-message",
    "event-list",
}
SUPPORTED_NODE_TYPES = {
    "input",
    "output",
    "router",
    "construct_message",
    "construct_content",
    "split_event",
    "construct_list",
    "list_append",
    "foreach",
    "history",
    "llm",
    "local_tool",
    "remote_sync_tool",
    "remote_async_tool",
    "context_create",
    "context_read",
    "context_write",
    "workflow",
}

NODE_BASE_FIELDS = {"id", "type", "name", "x", "y", "arguments"}
NODE_SHARED_FIELDS = {
    "workflowPorts",
    "dataInputPorts",
    "input_ports",
    "output_ports",
}
NODE_ARGUMENT_FIELDS_BY_TYPE = {
    "input": set(),
    "output": set(),
    "router": {"branches"},
    "construct_message": {"role"},
    "construct_content": {"append_items"},
    "split_event": set(),
    "construct_list": {"item_type", "initial_value_count"},
    "list_append": {"item_type", "position"},
    "foreach": {"item_type"},
    "history": {"event_types", "limit"},
    "llm": {"model", "think", "tool_calls", "tools"},
    "local_tool": {"tool", "parameters"},
    "remote_sync_tool": {"tool", "parameters", "outputs", "timeout_ms"},
    "remote_async_tool": {"tool", "parameters", "timeout_ms", "callback"},
    "context_create": {"value_type"},
    "context_read": {"value_type"},
    "context_write": {"value_type"},
    "workflow": {"workflow_name"},
}
NODE_ARGUMENT_FIELDS = set().union(*NODE_ARGUMENT_FIELDS_BY_TYPE.values())


def node_arguments(node: dict[str, Any]) -> dict[str, Any]:
    arguments = node.get("arguments")
    return arguments if isinstance(arguments, dict) else {}


def node_argument(node: dict[str, Any], name: str, default: Any = None) -> Any:
    return node_arguments(node).get(name, default)


def list_type_for_item(item_type: Any) -> str:
    return "event-list" if item_type == "event" else f"list-{item_type}"


def tool_parameter_names(node: dict[str, Any]) -> list[str]:
    parameters = node_argument(node, "parameters", [])
    if node.get("type") in {"remote_sync_tool", "remote_async_tool"}:
        return [parameter["name"] for parameter in parameters]
    return parameters


def tool_parameter_type(node: dict[str, Any], name: str) -> str | None:
    if node.get("type") == "local_tool":
        return "content" if name in tool_parameter_names(node) else None
    if node.get("type") in {"remote_sync_tool", "remote_async_tool"}:
        return next(
            (parameter["type"] for parameter in node_argument(node, "parameters", []) if parameter["name"] == name),
            None,
        )
    return None


def tool_output_type(node: dict[str, Any], name: str) -> str | None:
    if node.get("type") == "local_tool" and name == "output":
        return "content"
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
    if node_type == "router":
        return declared_inputs | {"content-in"}, set()
    if node_type == "llm":
        outputs = {"output"}
        if node_argument(node, "think") is True:
            outputs.add("reasoning")
        if node_argument(node, "tool_calls") is True:
            outputs.add("tool_calls")
        return {"messages-in"}, outputs
    if node_type == "construct_message":
        return declared_inputs | {"content-in"}, {"message-out"}
    if node_type == "construct_content":
        return declared_inputs, {"content-out"}
    if node_type == "split_event":
        return declared_inputs | {"event-in"}, {"type-out", "payload-out"}
    if node_type == "construct_list":
        return declared_inputs, {"list-out"}
    if node_type == "list_append":
        return declared_inputs | {"list-in", "item-in"}, {"list-out"}
    if node_type == "foreach":
        return declared_inputs | {"list-in"}, {"item-out"}
    if node_type == "history":
        return declared_inputs, {"events"}
    if node_type == "local_tool":
        return declared_inputs | set(tool_parameter_names(node)), {"output"}
    if node_type == "remote_sync_tool":
        return declared_inputs | set(tool_parameter_names(node)), {
            output["name"] for output in node_argument(node, "outputs", [])
        }
    if node_type == "remote_async_tool":
        return declared_inputs | set(tool_parameter_names(node)), {"task_id"}
    if node_type == "context_create":
        return {"initial-value"}, {"context-id"}
    if node_type == "context_read":
        return {"context-id"}, {"value-out"}
    if node_type == "context_write":
        return {"context-id", "value-in"}, {"context-id", "value-out"}
    if node_type == "workflow":
        return (
            {f"workflow:{port['name']}" for port in node.get("input_ports", [])},
            {f"workflow:{port['name']}" for port in node.get("output_ports", [])},
        )
    return declared_inputs, set()


def control_ports_for_node(node: dict[str, Any]) -> tuple[set[str], set[str]]:
    node_type = node["type"]
    if node_type == "input":
        return set(), {"control-out"}
    if node_type == "output":
        return {"control-in"}, set()
    if node_type == "router":
        return {"control-in"}, {
            branch["id"] for branch in node_argument(node, "branches", [])
        }
    if node_type == "foreach":
        return {"control-in", "loop-in"}, {"control-out", "loop-out"}
    return {"control-in"}, {"control-out"}


def is_valid_connection(
    connection: Any,
    nodes_by_id: dict[str, dict[str, Any]],
    input_ports: list[dict[str, Any]],
    output_ports: list[dict[str, Any]],
) -> bool:
    if not isinstance(connection, dict):
        return False
    from_id = connection.get("fromId")
    to_id = connection.get("toId")
    from_port = connection.get("fromPortId")
    to_port = connection.get("toPortId")
    connection_type = connection.get("type")
    if not all(isinstance(value, str) and value for value in (from_id, to_id, from_port, to_port)):
        return False
    source_node = nodes_by_id.get(from_id)
    target_node = nodes_by_id.get(to_id)
    if source_node is None or target_node is None:
        return False
    try:
        if connection_type == "control":
            source_inputs, source_outputs = control_ports_for_node(source_node)
            target_inputs, target_outputs = control_ports_for_node(target_node)
            return from_port in source_outputs and to_port in target_inputs
        if connection_type not in DATA_CONNECTION_TYPES:
            return False
        _, source_outputs = data_ports_for_node(source_node, input_ports, output_ports)
        target_inputs, _ = data_ports_for_node(target_node, input_ports, output_ports)
        if from_port not in source_outputs or to_port not in target_inputs:
            return False
        if source_node["type"] == "input":
            source_port = next(port for port in boundary_ports(input_ports) if port["id"] == from_port)
            if connection_type != source_port["type"]:
                return False
        if target_node["type"] == "output":
            target_port = next(port for port in boundary_ports(output_ports) if port["id"] == to_port)
            if connection_type != target_port["type"]:
                return False
        if source_node["type"] == "workflow":
            source_port = next(port for port in source_node.get("output_ports", []) if f"workflow:{port['name']}" == from_port)
            if connection_type != source_port["type"]:
                return False
        if target_node["type"] == "workflow":
            target_port = next(port for port in target_node.get("input_ports", []) if f"workflow:{port['name']}" == to_port)
            if connection_type != target_port["type"]:
                return False
        if target_node["type"] in {"local_tool", "remote_sync_tool", "remote_async_tool"} and connection_type != tool_parameter_type(target_node, to_port):
            return False
        if source_node["type"] in {"local_tool", "remote_sync_tool", "remote_async_tool"} and connection_type != tool_output_type(source_node, from_port):
            return False
        if target_node["type"] in {"context_create", "context_write"}:
            value_port = "initial-value" if target_node["type"] == "context_create" else "value-in"
            expected_type = node_argument(target_node, "value_type") if to_port == value_port else "content"
            if connection_type != expected_type:
                return False
        if target_node["type"] == "context_read" and connection_type != "content":
            return False
        if source_node["type"] == "context_create" and connection_type != "content":
            return False
        if source_node["type"] in {"context_read", "context_write"}:
            expected_type = "content" if from_port == "context-id" else node_argument(source_node, "value_type")
            if connection_type != expected_type:
                return False
        if source_node["type"] == "history" and (from_port != "events" or connection_type != "event-list"):
            return False
        if target_node["type"] == "split_event" and (to_port != "event-in" or connection_type != "event"):
            return False
        if source_node["type"] == "split_event":
            if from_port not in {"type-out", "payload-out"} or connection_type != "content":
                return False
        source_type = source_node["type"]
        target_type = target_node["type"]
        if target_type == "construct_list" and connection_type != node_argument(target_node, "item_type"):
            return False
        if source_type == "construct_list" and connection_type != list_type_for_item(node_argument(source_node, "item_type")):
            return False
        if target_type == "list_append":
            expected_type = (
                list_type_for_item(node_argument(target_node, "item_type"))
                if to_port == "list-in"
                else node_argument(target_node, "item_type")
            )
            if connection_type != expected_type:
                return False
        if source_type == "list_append" and connection_type != list_type_for_item(node_argument(source_node, "item_type")):
            return False
        if target_type == "foreach" and (connection_type != list_type_for_item(node_argument(target_node, "item_type")) or to_port != "list-in"):
            return False
        if source_type == "foreach" and (connection_type != node_argument(source_node, "item_type") or from_port != "item-out"):
            return False
        return not (source_type == "llm" and from_port == "tool_calls" and connection_type != "list-content")
    except (KeyError, StopIteration, TypeError):
        return False


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