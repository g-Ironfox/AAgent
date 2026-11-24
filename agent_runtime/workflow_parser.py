"""Compile a canvas workflow into an index-based linked-list structure."""

from __future__ import annotations

import json
import os
from typing import Any
from urllib.parse import quote

import requests
from workflow_contract import (
    boundary_ports,
    data_ports_for_node,
    node_argument,
    normalize_node_arguments,
)


class WorkflowParseError(ValueError):
    """Raised when a workflow cannot be loaded or compiled."""


WORKFLOW_SCHEMA_VERSION = "2.0"


def _node_struct_definitions(node: dict[str, Any], definitions: dict[str, Any]) -> dict[str, Any]:
    """Keep only types this node can validate, including nested dependencies.

    Node state is serialized at every scheduler step and in each function frame;
    copying the complete workflow type table into every node makes local
    functions unnecessarily expensive to persist.
    """
    value_types = [node_argument(node, key) for key in ("value_type", "item_type")]
    struct_id = node_argument(node, "struct_id")
    if struct_id:
        value_types.append("struct:" + struct_id)
    for key in ("workflowPorts", "function_ports", "input_ports", "output_ports"):
        value_types.extend(port.get("type") for port in node.get(key, []))
    for key in ("parameters", "outputs"):
        value_types.extend(port.get("type") for port in node_argument(node, key, []))
    selected = set()
    while value_types:
        kind = value_types.pop()
        if not isinstance(kind, str) or not kind.startswith(("struct:", "list-struct:")):
            continue
        sid = kind.split(":", 1)[1]
        if sid in selected or sid not in definitions:
            continue
        selected.add(sid)
        value_types.extend(field["type"] for field in definitions[sid]["fields"])
    return {sid: definition for sid, definition in definitions.items() if sid in selected}


def parse_workflow(workflow: dict[str, Any]) -> list[dict[str, Any]]:
    """Convert ``nodes`` and ``connections`` to an index-linked node list.

    Control-flow links contain node indexes. Data inputs contain one mutable
    slot in the form ``[node_index, port_id, value_or_default]``; data outputs
    contain endpoint lists.
    """
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
                "_struct_definitions": _node_struct_definitions(parsed_node, struct_definitions),
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
    if node.get("type") in {"json_tool", "spawn_and_wait_subprocess"} and port_id == "error-out":
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


def _read_workspace_workflow_record(
    selector: str, value: str, identifier: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Load workflow content and permission metadata through the guarded API."""
    base_url = os.getenv("WORKSPACE_API_URL", "http://agent_environment:8080").rstrip("/")
    headers = {}
    try:
        from workflow_nodes import current_workflow_process

        process = current_workflow_process.get()
    except ImportError:
        process = None
    if process:
        headers["X-AAgent-Process-ID"] = f"{process.process_id}:{process._workspace_token}"
    try:
        if selector == "name":
            response = requests.get(f"{base_url}/api/files", headers=headers, timeout=(3, 15))
            response.raise_for_status()
            matches = [item for item in response.json().get("items", []) if item.get("name") == value]
            if len(matches) > 1:
                raise WorkflowParseError(f"workflow filename is ambiguous: {identifier}")
            if not matches:
                raise WorkflowParseError(f"workflow file not found or unreadable: {identifier}")
            file_id = matches[0]["file_id"]
        else:
            file_id = value
        response = requests.get(
            f"{base_url}/api/files/{quote(file_id, safe='')}",
            headers=headers,
            timeout=(3, 15),
        )
        if response.status_code == 403:
            raise WorkflowParseError(f"workflow file read permission denied: {identifier}")
        if response.status_code == 404:
            raise WorkflowParseError(f"workflow file not found: {identifier}")
        response.raise_for_status()
        file = response.json()
    except requests.RequestException as error:
        raise WorkflowParseError("failed to read workspace workflow file") from error
    try:
        workflow = json.loads(file.get("content", ""))
    except (ValueError, TypeError) as error:
        raise WorkflowParseError(f"invalid workflow JSON in workspace file: {identifier}") from error
    if not isinstance(workflow, dict):
        raise WorkflowParseError(f"workflow file must contain a JSON object: {identifier}")
    return (
        workflow,
        file.get("permissions", {
            "runtime": {"read": 0, "write": 0},
            "required": {"read": 0, "write": 0},
        }),
    )


def _read_workspace_workflow_record_by_name(file_name: str):
    return _read_workspace_workflow_record("name", file_name, file_name)
