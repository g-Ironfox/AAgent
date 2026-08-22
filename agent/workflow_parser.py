"""Compile a canvas workflow into an index-based linked-list structure."""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

from pymongo import MongoClient
from pymongo.errors import PyMongoError
from workflow_contract import data_ports_for_node


class WorkflowParseError(ValueError):
    """Raised when a workflow cannot be loaded or compiled."""


def parse_workflow(workflow: dict[str, Any]) -> list[dict[str, Any]]:
    """Convert ``nodes`` and ``connections`` to an index-linked node list.

    Control-flow links contain node indexes. Data inputs contain one endpoint
    in the form ``[node_index, port_id]``; data outputs contain endpoint lists.
    """
    nodes = workflow["nodes"]
    connections = workflow["connections"]
    node_indexes = {node["id"]: index for index, node in enumerate(nodes)}
    linked_nodes: list[dict[str, Any]] = []
    for node in nodes:
        parsed_node = {
            key: value
            for key, value in node.items()
            if key not in {"x", "y", "dataInputPorts"}
        }
        if node.get("type") == "router":
            parsed_node["branches"] = [
                {**branch, "successor": None} for branch in node["branches"]
            ]
        input_ports, output_ports = data_ports_for_node(node)
        linked_nodes.append(
            {
                **parsed_node,
                "control_predecessors": [],
                "control_successors": [],
                "control_inputs": {},
                "control_outputs": {},
                "data_inputs": {port_id: None for port_id in input_ports},
                "data_outputs": {port_id: [] for port_id in output_ports},
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
            _append_unique(linked_nodes[from_index]["control_successors"], to_index)
            _append_unique(linked_nodes[to_index]["control_predecessors"], from_index)
            linked_nodes[from_index]["control_outputs"][from_port] = [
                to_index,
                to_port,
            ]
            linked_nodes[to_index]["control_inputs"].setdefault(to_port, []).append(
                [from_index, from_port]
            )
            if linked_nodes[from_index].get("type") == "router":
                branch = next(
                    branch
                    for branch in linked_nodes[from_index]["branches"]
                    if branch["id"] == from_port
                )
                branch["successor"] = to_index
        else:
            _append_output_endpoint(
                linked_nodes[from_index]["data_outputs"],
                from_port,
                [to_index, to_port],
            )
            linked_nodes[to_index]["data_inputs"][to_port] = [
                from_index,
                from_port,
            ]

    return linked_nodes


def _append_unique(items: list[int], value: int) -> None:
    if value not in items:
        items.append(value)


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