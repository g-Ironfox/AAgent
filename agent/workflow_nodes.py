"""Execute parsed workflow nodes synchronously."""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Callable

from workflow_contract import node_argument, tool_parameter_names


WorkflowMap = list[dict[str, Any]]
NodeHandler = Callable[[int, WorkflowMap], int]
WORKFLOW_END = -1
logger = logging.getLogger("aagent.workflow")


def read_workflow_input(node: dict[str, Any], port_id: str) -> tuple[bool, Any]:
    input_slot = node.get("data_inputs", {}).get(port_id)
    if not isinstance(input_slot, list) or len(input_slot) != 3:
        return False, None
    return input_slot[2] is not None, input_slot[2]


def propagate_workflow_output(
    workflow_map: WorkflowMap, node: dict[str, Any], port_id: str, value: Any
) -> None:
    for target_id, target_port in node.get("data_outputs", {}).get(port_id, []):
        target_slot = workflow_map[target_id].get("data_inputs", {}).get(target_port)
        if not isinstance(target_slot, list) or len(target_slot) != 3:
            raise ValueError(
                f"workflow target input is not connected: node {target_id}, "
                f"port {target_port}"
            )
        target_slot[2] = value


def next_successor(node: dict[str, Any], key: str = "next") -> int:
    successor = node.get("successors", {}).get(key)
    if not isinstance(successor, int):
        raise ValueError(
            f"workflow successor is not connected: node {node.get('id')}, key {key}"
        )
    return successor


def run_workflow_map(workflow_map: WorkflowMap, start: int) -> dict[str, Any]:
    current_id = start
    result: dict[str, Any] | None = None
    while current_id != WORKFLOW_END:
        node = workflow_map[current_id]
        handler = nodes_map.get(node.get("type"))
        if handler is None:
            raise ValueError(f"unsupported workflow node type: {node.get('type')}")
        current_id = handler(current_id, workflow_map)
        node_result = node.pop("_workflow_result", None)
        if isinstance(node_result, dict):
            result = node_result
    return result or {}


def workflow_input(current_id: int, workflow_map: WorkflowMap) -> int:
    return next_successor(workflow_map[current_id])


def workflow_output(current_id: int, workflow_map: WorkflowMap) -> int:
    node = workflow_map[current_id]
    output: dict[str, Any] = {}
    for port in node.get("workflowPorts", []):
        has_value, value = read_workflow_input(node, port["id"])
        if has_value:
            output[port["name"]] = value
    node["_workflow_result"] = output
    return WORKFLOW_END


def workflow_llm(current_id: int, workflow_map: WorkflowMap) -> int:
    from llm import chat_with_deepseek
    from tools.tool import registered_tools

    node = workflow_map[current_id]

    def message_order(port_id: str) -> int:
        return int(port_id.removeprefix("message-in-"))

    messages = []
    input_ports = sorted(
        (
            port_id
            for port_id in node["data_inputs"]
            if port_id.startswith("message-in-")
            and port_id.removeprefix("message-in-").isdigit()
        ),
        key=message_order,
    )
    for port_id in input_ports:
        has_value, value = read_workflow_input(node, port_id)
        if has_value:
            messages.append(value)
    prompt = node_argument(node, "prompt")
    if prompt:
        messages.insert(0, {"role": "system", "content": prompt})

    configured_tools = set(node_argument(node, "tools", []))
    tools = [
        schema
        for schema in registered_tools
        if schema["function"]["name"] in configured_tools
    ]
    content, reasoning, tool_calls = chat_with_deepseek(messages, tools=tools)
    propagate_workflow_output(workflow_map, node, "output", content)
    if "reasoning" in node.get("data_outputs", {}):
        propagate_workflow_output(workflow_map, node, "reasoning", reasoning)
    if "tool_calls" in node.get("data_outputs", {}):
        propagate_workflow_output(
            workflow_map,
            node,
            "tool_calls",
            [json.dumps(tool_call, ensure_ascii=False) for tool_call in tool_calls],
        )
    return next_successor(node)


def workflow_construct_message(current_id: int, workflow_map: WorkflowMap) -> int:
    node = workflow_map[current_id]
    has_content, content = read_workflow_input(node, "content-in")
    if not has_content:
        raise ValueError(f"construct_message input is missing: node {node.get('id')}")
    message = {"role": node_argument(node, "role", "user"), "content": content}
    propagate_workflow_output(workflow_map, node, "message-out", message)
    return next_successor(node)


def workflow_construct_content(current_id: int, workflow_map: WorkflowMap) -> int:
    node = workflow_map[current_id]
    parts = []
    for item in node_argument(node, "append_items", []):
        if item.get("type") == "fixed":
            parts.append(item.get("value", ""))
            continue
        has_value, value = read_workflow_input(node, item["port_id"])
        if has_value:
            parts.append(value if isinstance(value, str) else str(value))
    propagate_workflow_output(workflow_map, node, "content-out", "".join(parts))
    return next_successor(node)


def workflow_construct_list(current_id: int, workflow_map: WorkflowMap) -> int:
    node = workflow_map[current_id]
    values = []
    for port_id in node.get("data_inputs", {}):
        has_value, value = read_workflow_input(node, port_id)
        if has_value:
            values.append(value)
    propagate_workflow_output(workflow_map, node, "list-out", values)
    return next_successor(node)


def workflow_foreach(current_id: int, workflow_map: WorkflowMap) -> int:
    node = workflow_map[current_id]
    items = node.get("_foreach_items")
    if items is None:
        has_items, input_items = read_workflow_input(node, "list-in")
        if not has_items:
            raise ValueError(f"foreach input is missing: node {node.get('id')}")
        if not isinstance(input_items, list):
            raise ValueError(f"foreach input must be a list: node {node.get('id')}")
        items = list(input_items)
        node["_foreach_items"] = items

    if not items:
        node.pop("_foreach_items", None)
        return next_successor(node)

    propagate_workflow_output(workflow_map, node, "item-out", items.pop(0))
    return next_successor(node, "item")


def workflow_router(current_id: int, workflow_map: WorkflowMap) -> int:
    node = workflow_map[current_id]
    has_key, key = read_workflow_input(node, "content-in")
    if not has_key:
        raise ValueError(f"router input is missing: node {node.get('id')}")
    return next_successor(node, f"branch-{key}")


def _tool_arguments(node: dict[str, Any]) -> dict[str, Any]:
    arguments = {}
    for parameter in tool_parameter_names(node):
        has_value, value = read_workflow_input(node, parameter)
        if has_value:
            arguments[parameter] = value
    return arguments


def _tool_output(result: Any) -> str:
    if isinstance(result, str):
        return result
    return json.dumps(result, ensure_ascii=False)


def workflow_local_tool(current_id: int, workflow_map: WorkflowMap) -> int:
    from tools.tool import execute_tool

    node = workflow_map[current_id]
    result = execute_tool(node["id"], node_argument(node, "tool"), _tool_arguments(node))
    propagate_workflow_output(workflow_map, node, "output", _tool_output(result))
    return next_successor(node)


def _call_remote_node(
    node: dict[str, Any],
    mode: str,
    default_timeout_env: str,
    default_timeout_ms: str,
    callback: dict[str, Any] | None = None,
) -> Any:
    from tool_server_client import ToolServerError, call_remote_tool

    tool = node_argument(node, "tool")
    timeout_ms = node_argument(
        node, "timeout_ms", int(os.getenv(default_timeout_env, default_timeout_ms))
    )
    try:
        return call_remote_tool(tool, _tool_arguments(node), mode, timeout_ms, callback)
    except ToolServerError as error:
        execution = "remote_sync" if mode == "wait" else "remote_async"
        details = {"node_id": node["id"], "tool": tool, "execution": execution, "message": str(error)}
        if error.task_id:
            details["task_id"] = error.task_id
        logger.error("remote tool failed: %s", json.dumps(details, ensure_ascii=False))
        raise ValueError(json.dumps(details, ensure_ascii=False)) from error


def workflow_remote_sync_tool(current_id: int, workflow_map: WorkflowMap) -> int:
    node = workflow_map[current_id]
    result = _call_remote_node(node, "wait", "TOOL_CLIENT_DEFAULT_WAIT_MS", "10000")
    outputs = node_argument(node, "outputs", [])
    if len(outputs) == 1 and outputs[0]["name"] == "result":
        propagate_workflow_output(workflow_map, node, "result", result)
    elif isinstance(result, dict):
        missing = [output["name"] for output in outputs if output["name"] not in result]
        if missing:
            raise ValueError(f"remote sync tool result is missing outputs: {', '.join(missing)}")
        for output in outputs:
            propagate_workflow_output(workflow_map, node, output["name"], result[output["name"]])
    elif outputs:
        raise ValueError("remote sync tool result must be an object for named outputs")
    return next_successor(node)


def workflow_remote_async_tool(current_id: int, workflow_map: WorkflowMap) -> int:
    node = workflow_map[current_id]
    task_id = _call_remote_node(
        node,
        "async",
        "TOOL_CLIENT_DEFAULT_ASYNC_TIMEOUT_MS",
        "600000",
        node_argument(node, "callback"),
    )
    propagate_workflow_output(workflow_map, node, "task_id", task_id)
    return next_successor(node)


def workflow_workflow(current_id: int, workflow_map: WorkflowMap) -> int:
    from workflow_parser import _read_workflow, parse_workflow
    from workflow_validator import validate_workflow

    parent_node = workflow_map[current_id]
    workflow_name = node_argument(parent_node, "workflow_name")
    call_stack = parent_node.get("_workflow_call_stack", [])
    if workflow_name in call_stack:
        chain = " -> ".join([*call_stack, workflow_name])
        raise ValueError(f"recursive workflow call detected: {chain}")

    workflow_document = _read_workflow(workflow_name)
    validate_workflow(workflow_document)
    if (
        parent_node.get("input_ports", [])
        != workflow_document.get("input_ports", [])
        or parent_node.get("output_ports", [])
        != workflow_document.get("output_ports", [])
    ):
        raise ValueError(
            "callable workflow contract changed; refresh the workflow node metadata: "
            f"{workflow_name}"
        )

    child_map = parse_workflow(workflow_document)
    child_input_id = next(
        (index for index, node in enumerate(child_map) if node["type"] == "input"),
        None,
    )
    if child_input_id is None:
        raise ValueError(f"callable workflow has no input node: {workflow_name}")

    next_call_stack = [*call_stack, workflow_name]
    for child_node in child_map:
        child_node["_workflow_call_stack"] = next_call_stack
    child_input = child_map[child_input_id]
    for port in child_input.get("workflowPorts", []):
        has_value, value = read_workflow_input(
            parent_node, f"workflow:{port['name']}"
        )
        if has_value:
            propagate_workflow_output(child_map, child_input, port["id"], value)

    output = run_workflow_map(child_map, child_input_id)
    for name, value in output.items():
        propagate_workflow_output(
            workflow_map, parent_node, f"workflow:{name}", value
        )
    return next_successor(parent_node)


nodes_map: dict[str, NodeHandler] = {
    "input": workflow_input,
    "output": workflow_output,
    "router": workflow_router,
    "construct_message": workflow_construct_message,
    "construct_content": workflow_construct_content,
    "construct_list": workflow_construct_list,
    "foreach": workflow_foreach,
    "llm": workflow_llm,
    "local_tool": workflow_local_tool,
    "remote_sync_tool": workflow_remote_sync_tool,
    "remote_async_tool": workflow_remote_async_tool,
    "workflow": workflow_workflow,
}