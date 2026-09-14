"""Compile a canvas workflow into an index-based linked-list structure."""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

from pymongo import MongoClient
from pymongo.errors import PyMongoError
from workflow_contract import (
    boundary_ports,
    data_ports_for_node,
    filter_connections,
    node_argument,
    normalize_node_arguments,
)


class WorkflowParseError(ValueError):
    """Raised when a workflow cannot be loaded or compiled."""


def parse_workflow(workflow: dict[str, Any]) -> list[dict[str, Any]]:
    """Convert ``nodes`` and ``connections`` to an index-linked node list.

    Control-flow links contain node indexes. Data inputs contain one mutable
    slot in the form ``[node_index, port_id, value_or_default]``; data outputs
    contain endpoint lists.
    """
    nodes = workflow["nodes"]
    connections = filter_connections(
        workflow["connections"],
        nodes,
        workflow["input_ports"],
        workflow["output_ports"],
    )
    input_ports = workflow["input_ports"]
    output_ports = workflow["output_ports"]
    node_indexes = {node["id"]: index for index, node in enumerate(nodes)}
    linked_nodes: list[dict[str, Any]] = []
    for node in nodes:
        parsed_node = normalize_node_arguments(node)
        parsed_node.pop("x", None)
        parsed_node.pop("y", None)
        if node.get("type") == "input":
            parsed_node["workflowPorts"] = boundary_ports(input_ports)
        elif node.get("type") == "output":
            parsed_node["workflowPorts"] = boundary_ports(output_ports)
        node_input_ports, node_output_ports = data_ports_for_node(
            node, input_ports, output_ports
        )
        linked_nodes.append(
            {
                **parsed_node,
                "predecessors": {},
                "successors": {},
                "data_inputs": {
                    port_id: [None, None, None] for port_id in node_input_ports
                },
                "data_outputs": {port_id: [] for port_id in node_output_ports},
            }
        )

    for connection in connections:
        from_id = connection["fromId"]
        to_id = connection["toId"]
        from_index = node_indexes[from_id]
        to_index = node_indexes[to_id]
        from_port = connection["fromPortId"]
        to_port = connection["toPortId"]
        connection_type = connection["type"]
        if connection_type == "control":
            successor_key = _successor_key(linked_nodes[from_index], from_port)
            predecessor_key = _predecessor_key(linked_nodes[to_index], to_port)
            linked_nodes[from_index]["successors"][successor_key] = to_index
            linked_nodes[to_index]["predecessors"].setdefault(
                predecessor_key, []
            ).append(from_index)
        else:
            _append_output_endpoint(
                linked_nodes[from_index]["data_outputs"],
                from_port,
                [to_index, to_port],
            )
            linked_nodes[to_index]["data_inputs"][to_port] = [
                from_index,
                from_port,
                None,
            ]

    return linked_nodes


def _successor_key(node: dict[str, Any], port_id: str) -> str:
    if node.get("type") == "router":
        branch = next(
            branch
            for branch in node_argument(node, "branches", [])
            if branch["id"] == port_id
        )
        return f"branch-{branch['name']}"
    if node.get("type") == "foreach" and port_id == "loop-out":
        return "item"
    return "next"


def _predecessor_key(node: dict[str, Any], port_id: str) -> str:
    if node.get("type") == "foreach" and port_id == "loop-in":
        return "continue"
    return "last"


def _append_output_endpoint(
    ports: dict[str, list[list[Any]]], port_id: str, endpoint: list[Any]
) -> None:
    endpoints = ports.setdefault(port_id, [])
    if endpoint not in endpoints:
        endpoints.append(endpoint)


def _read_workflow(workflow_name: str, *, by_id: bool = False) -> dict[str, Any]:
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
        if by_id:
            from bson import ObjectId
            from bson.errors import InvalidId

            try:
                query = {"_id": ObjectId(workflow_name)}
            except (InvalidId, TypeError):
                raise WorkflowParseError(f"workflow id invalid: {workflow_name}")
        else:
            query = {"name": workflow_name}
        workflow = client[database_name][collection_name].find_one(query, {"_id": False})
    if workflow is None:
        raise WorkflowParseError(f"workflow not found: {workflow_name}")
    return workflow


if __name__ =="__main__":
    workflow_name = sys.argv[1] if len(sys.argv) > 1 else ""
    result = parse_workflow(_read_workflow(workflow_name))
    for i in result:
        print(i)