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
    for index, node in enumerate(nodes):
        if not isinstance(node, dict):
            raise WorkflowParseError(f"nodes[{index}] must be an object")
        node_id = node.get("id")
        if not isinstance(node_id, str) or not node_id:
            raise WorkflowParseError(f"nodes[{index}].id must be a non-empty string")
        if node_id in node_indexes:
            raise WorkflowParseError(f"duplicate node id: {node_id}")

        node_indexes[node_id] = index
        parsed_node = {
            key: value for key, value in node.items() if key not in {"x", "y"}
        }
        if node.get("type") == "router":
            branches = node.get("branches")
            if not isinstance(branches, list):
                raise WorkflowParseError(f"nodes[{index}].branches must be a list")
            parsed_node["branches"] = [
                {**branch, "successor": None} for branch in branches
            ]
        data_inputs, data_outputs = _data_ports(node)
        linked_nodes.append(
            {
                **parsed_node,
                "control_predecessors": [],
                "control_successors": [],
                "data_inputs": data_inputs,
                "data_outputs": data_outputs,
            }
        )

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
            _append_unique(linked_nodes[from_index]["control_successors"], to_index)
            _append_unique(linked_nodes[to_index]["control_predecessors"], from_index)
            if linked_nodes[from_index].get("type") == "router":
                from_port = _port_id(connection, index, "fromPortId")
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
        elif connection_type == "content":
            from_port = _port_id(connection, index, "fromPortId")
            to_port = _port_id(connection, index, "toPortId")
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
                f"connections[{index}].type must be 'control' or 'content'"
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


def _data_ports(
    node: dict[str, Any],
) -> tuple[dict[str, list[Any] | None], dict[str, list[list[Any]]]]:
    node_type = node.get("type")
    if node_type == "input":
        return {}, {"content-out": []}
    if node_type == "router":
        return {"content-in": None}, {}
    if node_type == "llm":
        outputs: dict[str, list[list[Any]]] = {"output": []}
        if node.get("think") is True:
            outputs["reasoning"] = []
        if node.get("tool_calls") is True:
            outputs["tool_calls"] = []
        return {"content-in": None}, outputs
    if node_type == "tool":
        parameters = node.get("parameters", [])
        if not isinstance(parameters, list) or any(not isinstance(parameter, str) or not parameter for parameter in parameters):
            raise WorkflowParseError("tool node parameters must be a list of non-empty strings")
        return {parameter: None for parameter in parameters}, {"output": []}
    if node_type == "tool_calls":
        return {"tool_calls": None}, {"output": []}
    return {}, {}


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