"""Define workflow node types and their control/data ports."""

from __future__ import annotations

from typing import Any


DATA_CONNECTION_TYPES = {"content", "message", "list-content", "list-message"}
SUPPORTED_NODE_TYPES = {
    "input",
    "output",
    "router",
    "construct_message",
    "construct_content",
    "construct_list",
    "foreach",
    "llm",
    "tool",
    "tool_call",
    "workflow",
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
        if node.get("think") is True:
            outputs.add("reasoning")
        if node.get("tool_calls") is True:
            outputs.add("tool_calls")
        return declared_inputs, outputs
    if node_type == "construct_message":
        return declared_inputs | {"content-in"}, {"message-out"}
    if node_type == "construct_content":
        return declared_inputs, {"content-out"}
    if node_type == "construct_list":
        return declared_inputs, {"list-out"}
    if node_type == "foreach":
        return declared_inputs | {"list-in"}, {"item-out"}
    if node_type == "tool":
        return declared_inputs | set(node.get("parameters", [])), {"output"}
    if node_type == "workflow":
        return (
            {f"workflow:{port['name']}" for port in node.get("input_ports", [])},
            {f"workflow:{port['name']}" for port in node.get("output_ports", [])},
        )
    return declared_inputs | {"tool_call"}, {"tool_call_id", "result"}


def control_ports_for_node(node: dict[str, Any]) -> tuple[set[str], set[str]]:
    node_type = node["type"]
    if node_type == "input":
        return set(), {"control-out"}
    if node_type == "output":
        return {"control-in"}, set()
    if node_type == "router":
        return {"control-in"}, {branch["id"] for branch in node["branches"]}
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
            source_port = next(port for port in source_node["output_ports"] if f"workflow:{port['name']}" == from_port)
            if connection_type != source_port["type"]:
                return False
        if target_node["type"] == "workflow":
            target_port = next(port for port in target_node["input_ports"] if f"workflow:{port['name']}" == to_port)
            if connection_type != target_port["type"]:
                return False
        source_type = source_node["type"]
        target_type = target_node["type"]
        if target_type == "construct_list" and connection_type != target_node["item_type"]:
            return False
        if source_type == "construct_list" and connection_type != f"list-{source_node['item_type']}":
            return False
        if target_type == "foreach" and (connection_type != f"list-{target_node['item_type']}" or to_port != "list-in"):
            return False
        if source_type == "foreach" and (connection_type != source_node["item_type"] or from_port != "item-out"):
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