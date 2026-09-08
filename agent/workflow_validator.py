"""Validate canvas workflow structure and port contracts."""

from __future__ import annotations

from typing import Any

from workflow_contract import (
    DATA_CONNECTION_TYPES,
    SUPPORTED_NODE_TYPES,
    boundary_ports,
    control_ports_for_node,
    data_ports_for_node,
    filter_connections,
)


class WorkflowValidationError(ValueError):
    """Raised when a workflow violates its node or connection contract."""


def validate_workflow(workflow: dict[str, Any]) -> None:
    nodes = workflow.get("nodes")
    connections = workflow.get("connections")
    if not isinstance(nodes, list):
        raise WorkflowValidationError("workflow.nodes must be a list")
    if not isinstance(connections, list):
        raise WorkflowValidationError("workflow.connections must be a list")
    input_ports = _validate_boundary_metadata(workflow, "input_ports")
    output_ports = _validate_boundary_metadata(workflow, "output_ports")

    node_by_id: dict[str, dict[str, Any]] = {}
    for index, node in enumerate(nodes):
        _validate_node(node, index)
        if node["type"] in {"input", "output"}:
            expected_ports = boundary_ports(
                input_ports if node["type"] == "input" else output_ports
            )
            if node["workflowPorts"] != expected_ports:
                raise WorkflowValidationError(
                    f"nodes[{index}].workflowPorts must match workflow {node['type']}_ports"
                )
        node_id = node["id"]
        if node_id in node_by_id:
            raise WorkflowValidationError(f"duplicate node id: {node_id}")
        node_by_id[node_id] = node

    input_count = sum(node["type"] == "input" for node in nodes)
    if input_count != 1:
        raise WorkflowValidationError(
            f"workflow must contain exactly one input node, found {input_count}"
        )
    if not any(node["type"] == "output" for node in nodes):
        raise WorkflowValidationError("workflow must contain at least one output node")

    connected_control_inputs: dict[str, set[str]] = {
        node_id: set() for node_id in node_by_id
    }
    connected_control_outputs: dict[str, set[str]] = {
        node_id: set() for node_id in node_by_id
    }
    connected_data_inputs: set[tuple[str, str]] = set()

    valid_connections = filter_connections(connections, nodes, input_ports, output_ports)
    for index, connection in enumerate(valid_connections):
        if not isinstance(connection, dict):
            raise WorkflowValidationError(f"connections[{index}] must be an object")
        from_id = connection.get("fromId")
        to_id = connection.get("toId")
        if from_id not in node_by_id:
            raise WorkflowValidationError(
                f"connections[{index}].fromId references unknown node: {from_id}"
            )
        if to_id not in node_by_id:
            raise WorkflowValidationError(
                f"connections[{index}].toId references unknown node: {to_id}"
            )

        from_port = _port_id(connection, index, "fromPortId")
        to_port = _port_id(connection, index, "toPortId")
        connection_type = connection.get("type")
        source_node = node_by_id[from_id]
        target_node = node_by_id[to_id]
        if connection_type == "control":
            _validate_control_connection(
                source_node, from_port, target_node, to_port, index
            )
            if from_port in connected_control_outputs[from_id]:
                raise WorkflowValidationError(
                    f"control output has multiple successors: node {from_id}, port {from_port}"
                )
            connected_control_outputs[from_id].add(from_port)
            connected_control_inputs[to_id].add(to_port)
        elif connection_type in DATA_CONNECTION_TYPES:
            _validate_data_connection(
                source_node,
                from_port,
                target_node,
                to_port,
                connection_type,
                index,
                input_ports,
                output_ports,
            )
            target_endpoint = (to_id, to_port)
            if target_endpoint in connected_data_inputs:
                raise WorkflowValidationError(
                    f"data input has multiple sources: node {to_id}, port {to_port}"
                )
            connected_data_inputs.add(target_endpoint)
        else:
            raise WorkflowValidationError(
                f"connections[{index}].type must be a supported control or data type"
            )

    for node_id, node in node_by_id.items():
        required_inputs, required_outputs = control_ports_for_node(node)
        missing_inputs = required_inputs - connected_control_inputs[node_id]
        missing_outputs = required_outputs - connected_control_outputs[node_id]
        if missing_inputs or missing_outputs:
            missing = [
                *(f"input:{port_id}" for port_id in sorted(missing_inputs)),
                *(f"output:{port_id}" for port_id in sorted(missing_outputs)),
            ]
            raise WorkflowValidationError(
                f"control ports must be connected: node {node_id}, ports {', '.join(missing)}"
            )


def _validate_node(node: Any, index: int) -> None:
    if not isinstance(node, dict):
        raise WorkflowValidationError(f"nodes[{index}] must be an object")
    node_id = node.get("id")
    if not isinstance(node_id, str) or not node_id:
        raise WorkflowValidationError(f"nodes[{index}].id must be a non-empty string")
    node_type = node.get("type")
    if node_type not in SUPPORTED_NODE_TYPES:
        raise WorkflowValidationError(f"unsupported node type: {node_type}")
    _validate_declared_data_inputs(node, index)

    if node_type in {"input", "output"}:
        _validate_workflow_ports(node, index)

    if node_type == "router":
        branches = node.get("branches")
        if not isinstance(branches, list) or not branches:
            raise WorkflowValidationError(f"nodes[{index}].branches must be a non-empty list")
        branch_ids = [
            branch.get("id") if isinstance(branch, dict) else None
            for branch in branches
        ]
        if any(not isinstance(branch_id, str) or not branch_id for branch_id in branch_ids):
            raise WorkflowValidationError(
                f"nodes[{index}].branches must contain non-empty ids"
            )
        if len(branch_ids) != len(set(branch_ids)):
            raise WorkflowValidationError(f"nodes[{index}].branches contains duplicate ids")
    elif node_type == "construct_content":
        _validate_construct_content(node)
    elif node_type == "construct_list":
        _validate_construct_list(node)
    elif node_type == "foreach":
        if node.get("item_type") not in {"content", "message"}:
            raise WorkflowValidationError(
                "foreach node item_type must be 'content' or 'message'"
            )
    elif node_type == "tool":
        parameters = node.get("parameters", [])
        if not isinstance(parameters, list) or any(
            not isinstance(parameter, str) or not parameter for parameter in parameters
        ):
            raise WorkflowValidationError(
                "tool node parameters must be a list of non-empty strings"
            )
        if len(parameters) != len(set(parameters)):
            raise WorkflowValidationError("tool node parameters contains duplicates")
    elif node_type == "workflow":
        workflow_id = node.get("workflow_id")
        if not isinstance(workflow_id, str) or not workflow_id:
            raise WorkflowValidationError("workflow node workflow_id must be a non-empty string")
        _validate_callable_workflow_ports(node, "input_ports")
        _validate_callable_workflow_ports(node, "output_ports")


def _validate_boundary_metadata(
    workflow: dict[str, Any], field: str
) -> list[dict[str, Any]]:
    ports = workflow.get(field)
    if not isinstance(ports, list):
        raise WorkflowValidationError(f"workflow.{field} must be a list")
    _validate_callable_workflow_ports({field: ports}, field)
    return ports


def _validate_callable_workflow_ports(node: dict[str, Any], field: str) -> None:
    ports = node.get(field)
    if not isinstance(ports, list):
        raise WorkflowValidationError(f"workflow node {field} must be a list")
    names = []
    for port in ports:
        if not isinstance(port, dict) or not isinstance(port.get("name"), str) or not port["name"]:
            raise WorkflowValidationError(f"workflow node {field} must contain named ports")
        if port.get("type") not in DATA_CONNECTION_TYPES:
            raise WorkflowValidationError(f"workflow node {field} contains an unsupported type")
        names.append(port["name"].strip().casefold())
    if any(not name for name in names):
        raise WorkflowValidationError(f"workflow node {field} contains an empty name")
    if len(names) != len(set(names)):
        raise WorkflowValidationError(f"workflow node {field} contains duplicate names")


def _validate_declared_data_inputs(node: dict[str, Any], index: int) -> None:
    declared_inputs = node.get("dataInputPorts", [])
    if not isinstance(declared_inputs, list) or any(
        not isinstance(port_id, str) or not port_id for port_id in declared_inputs
    ):
        raise WorkflowValidationError(
            f"nodes[{index}].dataInputPorts must be a list of non-empty strings"
        )
    if len(declared_inputs) != len(set(declared_inputs)):
        raise WorkflowValidationError(
            f"nodes[{index}].dataInputPorts contains duplicate ports"
        )


def _validate_workflow_ports(node: dict[str, Any], index: int) -> None:
    if "workflowPorts" not in node:
        raise WorkflowValidationError(
            f"nodes[{index}].workflowPorts is required for {node['type']} nodes"
        )
    ports = node.get("workflowPorts", [])
    if not isinstance(ports, list):
        raise WorkflowValidationError(f"nodes[{index}].workflowPorts must be a list")
    port_ids = []
    port_names = []
    for port_index, port in enumerate(ports):
        if not isinstance(port, dict):
            raise WorkflowValidationError(
                f"nodes[{index}].workflowPorts[{port_index}] must be an object"
            )
        port_id = port.get("id")
        name = port.get("name")
        if not isinstance(port_id, str) or not port_id.startswith("workflow:"):
            raise WorkflowValidationError(
                f"nodes[{index}].workflowPorts[{port_index}].id must use the workflow: namespace"
            )
        if not isinstance(name, str) or not name or port_id != f"workflow:{name}":
            raise WorkflowValidationError(
                f"nodes[{index}].workflowPorts[{port_index}] id must match its name"
            )
        if port.get("type") not in DATA_CONNECTION_TYPES:
            raise WorkflowValidationError(
                f"nodes[{index}].workflowPorts[{port_index}].type is unsupported"
            )
        port_ids.append(port_id.casefold())
        port_names.append(name.strip().casefold())
    if len(port_ids) != len(set(port_ids)) or len(port_names) != len(set(port_names)):
        raise WorkflowValidationError(f"nodes[{index}].workflowPorts contains duplicates")


def _validate_construct_content(node: dict[str, Any]) -> None:
    append_items = node.get("append_items", [])
    if not isinstance(append_items, list) or not append_items:
        raise WorkflowValidationError(
            "construct_content node append_items must be a non-empty list"
        )
    port_ids = []
    for index, item in enumerate(append_items):
        if not isinstance(item, dict) or item.get("type") not in {"port", "fixed"}:
            raise WorkflowValidationError(
                f"construct_content node append_items[{index}] must be a port or fixed item"
            )
        if item["type"] == "port":
            port_id = item.get("port_id")
            if not isinstance(port_id, str) or not port_id:
                raise WorkflowValidationError(
                    f"construct_content node append_items[{index}].port_id must be a non-empty string"
                )
            port_ids.append(port_id)
        elif not isinstance(item.get("value", ""), str):
            raise WorkflowValidationError(
                f"construct_content node append_items[{index}].value must be a string"
            )
    if set(node.get("dataInputPorts", [])) != set(port_ids):
        raise WorkflowValidationError(
            "construct_content node dataInputPorts must match port append_items"
        )
    if len(port_ids) != len(set(port_ids)):
        raise WorkflowValidationError(
            "construct_content node port append_items must have unique port_id values"
        )


def _validate_construct_list(node: dict[str, Any]) -> None:
    item_type = node.get("item_type")
    if item_type not in {"content", "message"}:
        raise WorkflowValidationError(
            "construct_list node item_type must be 'content' or 'message'"
        )
    initial_value_count = node.get("initial_value_count")
    if (
        not isinstance(initial_value_count, int)
        or isinstance(initial_value_count, bool)
        or not 0 <= initial_value_count <= 20
    ):
        raise WorkflowValidationError(
            "construct_list node initial_value_count must be an integer from 0 to 20"
        )
    expected_inputs = {
        f"{item_type}-in-{input_index}"
        for input_index in range(initial_value_count)
    }
    if set(node.get("dataInputPorts", [])) != expected_inputs:
        raise WorkflowValidationError(
            "construct_list node dataInputPorts must match item_type and initial_value_count"
        )


def _port_id(connection: dict[str, Any], index: int, field: str) -> str:
    port_id = connection.get(field)
    if not isinstance(port_id, str) or not port_id:
        raise WorkflowValidationError(
            f"connections[{index}].{field} must be a non-empty string"
        )
    return port_id


def _validate_control_connection(
    source_node: dict[str, Any],
    from_port: str,
    target_node: dict[str, Any],
    to_port: str,
    connection_index: int,
) -> None:
    _, valid_outputs = control_ports_for_node(source_node)
    valid_inputs, _ = control_ports_for_node(target_node)
    if from_port not in valid_outputs:
        raise WorkflowValidationError(
            f"connections[{connection_index}].fromPortId is invalid for {source_node['type']}: {from_port}"
        )
    if to_port not in valid_inputs:
        raise WorkflowValidationError(
            f"connections[{connection_index}].toPortId is invalid for {target_node['type']}: {to_port}"
        )


def _validate_data_connection(
    source_node: dict[str, Any],
    from_port: str,
    target_node: dict[str, Any],
    to_port: str,
    connection_type: str,
    connection_index: int,
    input_ports: list[dict[str, Any]],
    output_ports: list[dict[str, Any]],
) -> None:
    source_inputs, source_outputs = data_ports_for_node(
        source_node, input_ports, output_ports
    )
    target_inputs, target_outputs = data_ports_for_node(
        target_node, input_ports, output_ports
    )
    del source_inputs, target_outputs
    if from_port not in source_outputs:
        raise WorkflowValidationError(
            f"unknown data output: node {source_node['id']}, port {from_port}"
        )
    if to_port not in target_inputs:
        raise WorkflowValidationError(
            f"unknown data input: node {target_node['id']}, port {to_port}"
        )

    if source_node["type"] == "input":
        source_port = next(port for port in boundary_ports(input_ports) if port["id"] == from_port)
        if connection_type != source_port["type"]:
            raise WorkflowValidationError(
                f"workflow input port {from_port} requires {source_port['type']} data: connection {connection_index}"
            )
    if target_node["type"] == "output":
        target_port = next(port for port in boundary_ports(output_ports) if port["id"] == to_port)
        if connection_type != target_port["type"]:
            raise WorkflowValidationError(
                f"workflow output port {to_port} requires {target_port['type']} data: connection {connection_index}"
            )
    if source_node["type"] == "workflow":
        source_port = next(port for port in source_node["output_ports"] if f"workflow:{port['name']}" == from_port)
        if connection_type != source_port["type"]:
            raise WorkflowValidationError(
                f"callable workflow output {from_port} requires {source_port['type']} data: connection {connection_index}"
            )
    if target_node["type"] == "workflow":
        target_port = next(port for port in target_node["input_ports"] if f"workflow:{port['name']}" == to_port)
        if connection_type != target_port["type"]:
            raise WorkflowValidationError(
                f"callable workflow input {to_port} requires {target_port['type']} data: connection {connection_index}"
            )

    source_type = source_node["type"]
    target_type = target_node["type"]
    if target_type == "construct_list" and connection_type != target_node["item_type"]:
        raise WorkflowValidationError(
            f"construct_list input requires {target_node['item_type']} data: connection {connection_index}"
        )
    if source_type == "construct_list" and connection_type != f"list-{source_node['item_type']}":
        raise WorkflowValidationError(
            f"construct_list output requires list-{source_node['item_type']} data: connection {connection_index}"
        )
    if target_type == "foreach" and (
        connection_type != f"list-{target_node['item_type']}" or to_port != "list-in"
    ):
        raise WorkflowValidationError(
            f"foreach input requires list-{target_node['item_type']} data: connection {connection_index}"
        )
    if source_type == "foreach" and (
        connection_type != source_node["item_type"] or from_port != "item-out"
    ):
        raise WorkflowValidationError(
            f"foreach output requires {source_node['item_type']} data: connection {connection_index}"
        )
    if source_type == "llm" and from_port == "tool_calls" and connection_type != "list-content":
        raise WorkflowValidationError(
            f"llm tool_calls output requires list-content data: connection {connection_index}"
        )