"""Compile a canvas workflow into an index-based linked-list structure."""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

from pymongo import MongoClient
from pymongo.collation import Collation
from pymongo.errors import PyMongoError
from workflow_contract import (
    migrate_subprocess_workflow_format,
    boundary_ports,
    data_ports_for_node,
    node_argument,
    normalize_node_arguments,
)


class WorkflowParseError(ValueError):
    """Raised when a workflow cannot be loaded or compiled."""


WORKFLOW_SCHEMA_VERSION = "2.0"


def parse_workflow(workflow: dict[str, Any]) -> list[dict[str, Any]]:
    """Convert ``nodes`` and ``connections`` to an index-linked node list.

    Control-flow links contain node indexes. Data inputs contain one mutable
    slot in the form ``[node_index, port_id, value_or_default]``; data outputs
    contain endpoint lists.
    """
    workflow = migrate_subprocess_workflow_format(workflow)
    from workflow_functions import bind_function_interfaces
    workflow = bind_function_interfaces(workflow)
    if workflow.get("schema_version") != WORKFLOW_SCHEMA_VERSION:
        raise WorkflowParseError(
            f"unsupported workflow schema_version: {workflow.get('schema_version')!r}; "
            f"expected {WORKFLOW_SCHEMA_VERSION}"
        )
    nodes = workflow["nodes"]
    connections = workflow["connections"]
    input_ports = workflow["input_ports"]
    output_ports = workflow["output_ports"]
    from workflow_structs import validate_struct_definitions
    struct_definitions = validate_struct_definitions(workflow.get("metadata", {}).get("structs", []))
    function_names = {function["id"]: function["name"]
                      for function in workflow.get("metadata", {}).get("functions", [])}
    node_indexes = {node["id"]: index for index, node in enumerate(nodes)}
    linked_nodes: list[dict[str, Any]] = []
    for node in nodes:
        parsed_node = normalize_node_arguments(node)
        if node.get("type") == "function_input":
            parsed_node["_function_name"] = function_names[node["function_id"]]
        if node.get("type") in {"tool", "remote_async_tool"}:
            declaration = next((tool for tool in workflow.get("metadata", {}).get("tools", []) if tool["name"] == node_argument(node, "tool")), None)
            if declaration is None and node["type"] == "remote_async_tool":
                declaration = next((tool for tool in workflow.get("remote_tools", []) if tool["name"] == node_argument(node, "tool")), None)
            if declaration is None:
                raise WorkflowParseError("tool is not registered in metadata.tools")
            parsed_node["_tool_kind"] = declaration.get("kind", "remote")
        if node.get("type") == "llm":
            parsed_node["_metadata_tools"] = [
                {"name": tool["name"], "kind": tool.get("kind", "remote")}
                for tool in workflow.get("metadata", {}).get("tools", [])
            ]
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
                "_struct_definitions": struct_definitions,
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
    if node.get("type") == "json_tool" and port_id == "error-out":
        return "error"
    if node.get("type") == "router":
        if port_id == "branch$others":
            return "branch$others"
        branch = next(
            branch
            for branch in node_argument(node, "branches", [])
            if branch["id"] == port_id
        )
        return f"branch-{branch['name']}"
    if node.get("type") in {"foreach", "while_pop"} and port_id == "loop-out":
        return "item"
    return "next"


def _predecessor_key(node: dict[str, Any], port_id: str) -> str:
    if node.get("type") in {"foreach", "while_pop"} and port_id == "loop-in":
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
    return migrate_subprocess_workflow_format(workflow)


def _read_workspace_workflow_file(
    selector: str, value: str, identifier: str
) -> dict[str, Any]:
    """Load a live workflow file from the current workspace generation."""
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
    try:
        with MongoClient(**mongo_kwargs) as client:
            workspace = client[os.getenv("MONGO_DATABASE", "agent")][
                os.getenv("MONGO_WORKSPACE_FILE_COLLECTION", "workspace_files")
            ]
            meta = workspace.find_one({"_id": "_workspace_current_state"}, {"generation": 1})
            if meta is None or "generation" not in meta:
                raise WorkflowParseError("workspace is not initialized")
            generation = meta["generation"]
            selector_value = f"{generation}:{value}" if selector == "_id" else value
            query = {selector: selector_value, "generation": generation}
            if selector == "name":
                matches = list(workspace.find(
                    query, {"content": 1}, collation=Collation(locale="simple")
                ).limit(2))
                if len(matches) > 1:
                    raise WorkflowParseError(f"workflow filename is ambiguous: {identifier}")
                file = matches[0] if matches else None
            else:
                file = workspace.find_one(query, {"content": 1})
    except PyMongoError as error:
        raise WorkflowParseError("failed to read workspace workflow file") from error
    if file is None:
        raise WorkflowParseError(f"workflow file not found: {identifier}")
    try:
        workflow = json.loads(file.get("content", ""))
    except (ValueError, TypeError) as error:
        raise WorkflowParseError(f"invalid workflow JSON in workspace file: {identifier}") from error
    if not isinstance(workflow, dict):
        raise WorkflowParseError(f"workflow file must contain a JSON object: {identifier}")
    return migrate_subprocess_workflow_format(workflow)


def _read_workspace_workflow(file_id: str) -> dict[str, Any]:
    return _read_workspace_workflow_file("_id", file_id, file_id)


def _read_workspace_workflow_by_name(file_name: str) -> dict[str, Any]:
    """Resolve a callable workflow by its exact workspace filename."""
    return _read_workspace_workflow_file("name", file_name, file_name)


if __name__ =="__main__":
    workflow_name = sys.argv[1] if len(sys.argv) > 1 else ""
    result = parse_workflow(_read_workflow(workflow_name))
    for i in result:
        print(i)
