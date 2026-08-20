"""Compile a canvas workflow into an index-based linked-list structure."""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

from pymongo import MongoClient
from pymongo.errors import PyMongoError


class WorkflowParseError(ValueError):
    """Raised when a workflow cannot be converted safely."""


def parse_workflow(workflow: dict[str, Any]) -> list[dict[str, Any]]:
    """Convert ``nodes`` and ``connections`` to an index-linked node list.

    Control-flow links contain node indexes. Data inputs contain one endpoint
    in the form ``[node_index, port_id]``; data outputs contain endpoint lists.
    """
    nodes = workflow.get("nodes")
    connections = workflow.get("connections")
    if not isinstance(nodes, list):
        raise WorkflowParseError("workflow.nodes must be a list")
    if not isinstance(connections, list):
        raise WorkflowParseError("workflow.connections must be a list")

    node_indexes: dict[str, int] = {}
    linked_nodes: list[dict[str, Any]] = []
    output_count = 0
    for index, node in enumerate(nodes):
        if not isinstance(node, dict):
            raise WorkflowParseError(f"nodes[{index}] must be an object")
        node_id = node.get("id")
        if not isinstance(node_id, str) or not node_id:
            raise WorkflowParseError(f"nodes[{index}].id must be a non-empty string")
        if node_id in node_indexes:
            raise WorkflowParseError(f"duplicate node id: {node_id}")

        node_indexes[node_id] = index
        if node.get("type") == "output":
            output_count += 1
        parsed_node = {
            key: value
            for key, value in node.items()
            if key not in {"x", "y", "dataInputPorts"}
        }
        if node.get("type") == "router":
            branches = node.get("branches")
            if not isinstance(branches, list):
                raise WorkflowParseError(f"nodes[{index}].branches must be a list")
            parsed_node["branches"] = [
                {**branch, "successor": None} for branch in branches
            ]
        declared_inputs = _declared_data_inputs(node, index)
        data_inputs, data_outputs = _data_ports(node, declared_inputs)
        linked_nodes.append(
            {
                **parsed_node,
                "control_predecessors": [],
                "control_successors": [],
                "control_inputs": {},
                "control_outputs": {},
                "data_inputs": data_inputs,
                "data_outputs": data_outputs,
            }
        )

    if output_count == 0:
        raise WorkflowParseError("workflow must contain at least one output node")

    for index, connection in enumerate(connections):
        if not isinstance(connection, dict):
            raise WorkflowParseError(f"connections[{index}] must be an object")

        from_id = connection.get("fromId")
        to_id = connection.get("toId")
        if from_id not in node_indexes:
            raise WorkflowParseError(
                f"connections[{index}].fromId references unknown node: {from_id}"
            )
        if to_id not in node_indexes:
            raise WorkflowParseError(
                f"connections[{index}].toId references unknown node: {to_id}"
            )

        from_index = node_indexes[from_id]
        to_index = node_indexes[to_id]
        connection_type = connection.get("type")
        if connection_type == "control":
            from_port = _port_id(connection, index, "fromPortId")
            to_port = _port_id(connection, index, "toPortId")
            _validate_control_ports(nodes[from_index], from_port, nodes[to_index], to_port, index)
            _append_unique(linked_nodes[from_index]["control_successors"], to_index)
            _append_unique(linked_nodes[to_index]["control_predecessors"], from_index)
            _set_control_output(linked_nodes[from_index], from_port, to_index, to_port)
            linked_nodes[to_index]["control_inputs"].setdefault(to_port, []).append(
                [from_index, from_port]
            )
            if linked_nodes[from_index].get("type") == "router":
                branch = next(
                    (
                        branch
                        for branch in linked_nodes[from_index]["branches"]
                        if branch.get("id") == from_port
                    ),
                    None,
                )
                if branch is None:
                    raise WorkflowParseError(
                        f"connections[{index}].fromPortId references unknown branch: {from_port}"
                    )
                if branch["successor"] is not None:
                    raise WorkflowParseError(
                        f"router branch has multiple successors: {from_port}"
                    )
                branch["successor"] = to_index
        elif connection_type in {"content", "message", "list-content", "list-message"}:
            from_port = _port_id(connection, index, "fromPortId")
            to_port = _port_id(connection, index, "toPortId")
            target_node = nodes[to_index]
            source_node = nodes[from_index]
            if target_node.get("type") == "construct_list":
                item_type = target_node.get("item_type")
                if connection_type != item_type:
                    raise WorkflowParseError(
                        f"construct_list input requires {item_type} data: connection {index}"
                    )
            if source_node.get("type") == "construct_list":
                item_type = source_node.get("item_type")
                if connection_type != f"list-{item_type}":
                    raise WorkflowParseError(
                        f"construct_list output requires list-{item_type} data: connection {index}"
                    )
            if target_node.get("type") == "foreach":
                item_type = target_node.get("item_type")
                if connection_type != f"list-{item_type}" or to_port != "list-in":
                    raise WorkflowParseError(
                        f"foreach input requires list-{item_type} data: connection {index}"
                    )
            if source_node.get("type") == "foreach":
                item_type = source_node.get("item_type")
                if connection_type != item_type or from_port != "item-out":
                    raise WorkflowParseError(
                        f"foreach output requires {item_type} data: connection {index}"
                    )
            if source_node.get("type") == "llm" and from_port == "tool_calls":
                if connection_type != "list-content":
                    raise WorkflowParseError(
                        f"llm tool_calls output requires list-content data: connection {index}"
                    )
            data_outputs = linked_nodes[from_index]["data_outputs"]
            if from_port not in data_outputs:
                raise WorkflowParseError(
                    f"unknown data output: node {from_id}, port {from_port}"
                )
            _append_output_endpoint(
                data_outputs,
                from_port,
                [to_index, to_port],
            )
            data_inputs = linked_nodes[to_index]["data_inputs"]
            if to_port not in data_inputs:
                raise WorkflowParseError(
                    f"unknown data input: node {to_id}, port {to_port}"
                )
            if data_inputs[to_port] is not None:
                raise WorkflowParseError(
                    f"data input has multiple sources: node {to_id}, port {to_port}"
                )
            data_inputs[to_port] = [from_index, from_port]
        else:
            raise WorkflowParseError(
                f"connections[{index}].type must be a supported control or data type"
            )

    for node in linked_nodes:
        required_inputs, required_outputs = _required_control_ports(node)
        missing_inputs = required_inputs - set(node["control_inputs"])
        missing_outputs = required_outputs - set(node["control_outputs"])
        if missing_inputs or missing_outputs:
            missing = [
                *(f"input:{port_id}" for port_id in sorted(missing_inputs)),
                *(f"output:{port_id}" for port_id in sorted(missing_outputs)),
            ]
            raise WorkflowParseError(
                f"control ports must be connected: node {node.get('id')}, ports {', '.join(missing)}"
            )

    return linked_nodes


def _port_id(connection: dict[str, Any], index: int, field: str) -> str:
    port_id = connection.get(field)
    if not isinstance(port_id, str) or not port_id:
        raise WorkflowParseError(
            f"connections[{index}].{field} must be a non-empty string"
        )
    return port_id


def _append_unique(items: list[int], value: int) -> None:
    if value not in items:
        items.append(value)


def _required_control_ports(node: dict[str, Any]) -> tuple[set[str], set[str]]:
    node_type = node.get("type")
    if node_type == "input":
        return set(), {"control-out"}
    if node_type == "output":
        return {"control-in"}, set()
    if node_type == "router":
        return {"control-in"}, {
            branch["id"]
            for branch in node.get("branches", [])
            if isinstance(branch, dict) and isinstance(branch.get("id"), str)
        }
    if node_type == "foreach":
        return {"control-in", "loop-in"}, {"control-out", "loop-out"}
    return {"control-in"}, {"control-out"}


def _validate_control_ports(
    source_node: dict[str, Any],
    from_port: str,
    target_node: dict[str, Any],
    to_port: str,
    connection_index: int,
) -> None:
    source_type = source_node.get("type")
    if source_type == "router":
        valid_outputs = {
            branch.get("id")
            for branch in source_node.get("branches", [])
            if isinstance(branch, dict)
        }
    elif source_type == "foreach":
        valid_outputs = {"control-out", "loop-out"}
    elif source_type == "output":
        valid_outputs = set()
    else:
        valid_outputs = {"control-out"}

    target_type = target_node.get("type")
    if target_type == "input":
        valid_inputs = set()
    elif target_type == "foreach":
        valid_inputs = {"control-in", "loop-in"}
    else:
        valid_inputs = {"control-in"}
    if from_port not in valid_outputs:
        raise WorkflowParseError(
            f"connections[{connection_index}].fromPortId is invalid for {source_type}: {from_port}"
        )
    if to_port not in valid_inputs:
        raise WorkflowParseError(
            f"connections[{connection_index}].toPortId is invalid for {target_node.get('type')}: {to_port}"
        )


def _set_control_output(
    node: dict[str, Any], from_port: str, target_index: int, target_port: str
) -> None:
    outputs = node["control_outputs"]
    if from_port in outputs:
        raise WorkflowParseError(
            f"control output has multiple successors: node {node.get('id')}, port {from_port}"
        )
    outputs[from_port] = [target_index, target_port]


def _declared_data_inputs(
    node: dict[str, Any], index: int
) -> dict[str, list[Any] | None]:
    declared_inputs = node.get("dataInputPorts", [])
    if not isinstance(declared_inputs, list) or any(
        not isinstance(port_id, str) or not port_id
        for port_id in declared_inputs
    ):
        raise WorkflowParseError(
            f"nodes[{index}].dataInputPorts must be a list of non-empty strings"
        )
    if len(declared_inputs) != len(set(declared_inputs)):
        raise WorkflowParseError(
            f"nodes[{index}].dataInputPorts contains duplicate ports"
        )
    return {port_id: None for port_id in declared_inputs}


def _data_ports(
    node: dict[str, Any], data_inputs: dict[str, list[Any] | None]
) -> tuple[dict[str, list[Any] | None], dict[str, list[list[Any]]]]:
    node_type = node.get("type")
    if node_type == "input":
        return data_inputs, {"content-out": [], "source": []}
    if node_type == "output":
        data_inputs.setdefault("content-in", None)
        return data_inputs, {}
    if node_type == "router":
        data_inputs.setdefault("content-in", None)
        return data_inputs, {}
    if node_type == "llm":
        outputs: dict[str, list[list[Any]]] = {"output": []}
        if node.get("think") is True:
            outputs["reasoning"] = []
        if node.get("tool_calls") is True:
            outputs["tool_calls"] = []
        return data_inputs, outputs
    if node_type == "construct_message":
        data_inputs.setdefault("content-in", None)
        return data_inputs, {"message-out": []}
    if node_type == "construct_content":
        append_items = node.get("append_items", [])
        if not isinstance(append_items, list) or not append_items:
            raise WorkflowParseError(
                "construct_content node append_items must be a non-empty list"
            )
        expected_inputs = set()
        for index, item in enumerate(append_items):
            if not isinstance(item, dict) or item.get("type") not in {"port", "fixed"}:
                raise WorkflowParseError(
                    f"construct_content node append_items[{index}] must be a port or fixed item"
                )
            if item["type"] == "port":
                port_id = item.get("port_id")
                if not isinstance(port_id, str) or not port_id:
                    raise WorkflowParseError(
                        f"construct_content node append_items[{index}].port_id must be a non-empty string"
                    )
                expected_inputs.add(port_id)
            elif not isinstance(item.get("value", ""), str):
                raise WorkflowParseError(
                    f"construct_content node append_items[{index}].value must be a string"
                )
        if set(data_inputs) != expected_inputs:
            raise WorkflowParseError(
                "construct_content node dataInputPorts must match port append_items"
            )
        if len(expected_inputs) != sum(item["type"] == "port" for item in append_items):
            raise WorkflowParseError(
                "construct_content node port append_items must have unique port_id values"
            )
        return data_inputs, {"content-out": []}
    if node_type == "construct_list":
        item_type = node.get("item_type")
        if item_type not in {"content", "message"}:
            raise WorkflowParseError(
                "construct_list node item_type must be 'content' or 'message'"
            )
        initial_value_count = node.get("initial_value_count")
        if (
            not isinstance(initial_value_count, int)
            or isinstance(initial_value_count, bool)
            or not 0 <= initial_value_count <= 20
        ):
            raise WorkflowParseError(
                "construct_list node initial_value_count must be an integer from 0 to 20"
            )
        expected_inputs = {
            f"{item_type}-in-{index}" for index in range(initial_value_count)
        }
        if set(data_inputs) != expected_inputs:
            raise WorkflowParseError(
                "construct_list node dataInputPorts must match item_type and initial_value_count"
            )
        return data_inputs, {"list-out": []}
    if node_type == "foreach":
        item_type = node.get("item_type")
        if item_type not in {"content", "message"}:
            raise WorkflowParseError(
                "foreach node item_type must be 'content' or 'message'"
            )
        data_inputs.setdefault("list-in", None)
        return data_inputs, {"item-out": []}
    if node_type == "tool":
        parameters = node.get("parameters", [])
        if not isinstance(parameters, list) or any(not isinstance(parameter, str) or not parameter for parameter in parameters):
            raise WorkflowParseError("tool node parameters must be a list of non-empty strings")
        for parameter in parameters:
            data_inputs.setdefault(parameter, None)
        return data_inputs, {"output": []}
    if node_type == "tool_call":
        data_inputs.setdefault("tool_call", None)
        return data_inputs, {"tool_call_id": [], "result": []}
    raise WorkflowParseError(f"unsupported node type: {node_type}")


def _append_output_endpoint(
    ports: dict[str, list[list[Any]]], port_id: str, endpoint: list[Any]
) -> None:
    endpoints = ports.setdefault(port_id, [])
    if endpoint not in endpoints:
        endpoints.append(endpoint)


def _read_workflow(workflow_key: str) -> dict[str, Any]:
    mongo_kwargs: dict[str, Any] = {
        "host": os.getenv("MONGO_HOST", "mongodb"),
        "port": int(os.getenv("MONGO_PORT", "27017")),
        "serverSelectionTimeoutMS": 5000,
    }
    if os.getenv("MONGO_USER"):
        mongo_kwargs.update(
            username=os.environ["MONGO_USER"],
            password=os.getenv("MONGO_PASS", ""),
            authSource="admin",
        )

    database_name = os.getenv("MONGO_DATABASE", "agent")
    collection_name = os.getenv("MONGO_WORKFLOW_COLLECTION", "workflows")
    with MongoClient(**mongo_kwargs) as client:
        workflow = client[database_name][collection_name].find_one(
            {"key": workflow_key}, {"_id": False}
        )
    if workflow is None:
        raise WorkflowParseError(f"workflow not found: {workflow_key}")
    return workflow


if __name__ =="__main__":
    result = parse_workflow(_read_workflow("main"))
    for i in result:
        print(i)