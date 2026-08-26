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


def data_ports_for_node(node: dict[str, Any]) -> tuple[set[str], set[str]]:
    node_type = node["type"]
    declared_inputs = set(node.get("dataInputPorts", []))
    if node_type == "input":
        workflow_ports = node.get("workflowPorts", [])
        return declared_inputs, {port["id"] for port in workflow_ports} if "workflowPorts" in node else {"content-out", "source"}
    if node_type == "output":
        workflow_ports = node.get("workflowPorts", [])
        return declared_inputs | ({port["id"] for port in workflow_ports} if "workflowPorts" in node else {"content-in"}), set()
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