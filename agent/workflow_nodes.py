"""Execute parsed workflow nodes synchronously."""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Callable
from uuid import uuid4

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


def run_workflow_map(
    workflow_map: WorkflowMap,
    start: int,
) -> dict[str, Any]:
    from workflow_context_repository import WorkflowContextError, delete_contexts

    invocation_id = uuid4().hex
    context_ids: set[str] = set()
    for node in workflow_map:
        node["_workflow_invocation_id"] = invocation_id
        node["_workflow_context_ids"] = context_ids
    try:
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
    finally:
        try:
            delete_contexts(context_ids)
        except WorkflowContextError:
            logger.exception("failed to clean up Workflow Contexts")
        for node in workflow_map:
            node.pop("_workflow_invocation_id", None)
            node.pop("_workflow_context_ids", None)


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
    node = workflow_map[current_id]
    has_messages, value = read_workflow_input(node, "messages-in")
    if not has_messages:
        raise ValueError(f"llm messages input is missing: node {node.get('id')}")
    if not isinstance(value, list) or not value:
        raise ValueError(f"llm messages input must be a non-empty list: node {node.get('id')}")
    if any(
        not isinstance(message, dict)
        or message.get("role") not in {"system", "user", "assistant", "tool"}
        or not isinstance(message.get("content"), str)
        for message in value
    ):
        raise ValueError(f"llm messages input contains an invalid message: node {node.get('id')}")
    messages = list(value)

    from llm import chat_with_deepseek
    from tools.tool import registered_tools

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
    role = node_argument(node, "role", "user")
    if node_argument(node, "role_source", "fixed") == "port":
        has_role, role = read_workflow_input(node, "role-in")
        if not has_role:
            raise ValueError(f"construct_message role input is missing: node {node.get('id')}")
    if role not in {"system", "user", "assistant", "tool"}:
        raise ValueError(f"construct_message role is invalid: node {node.get('id')}")
    message = {"role": role, "content": content}
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


def workflow_content_map(current_id: int, workflow_map: WorkflowMap) -> int:
    node = workflow_map[current_id]
    has_content, content = read_workflow_input(node, "content-in")
    if not has_content:
        raise ValueError(f"content_map input is missing: node {node.get('id')}")
    if not isinstance(content, str):
        raise ValueError(f"content_map input must be content: node {node.get('id')}")
    mappings = {
        item["key"]: item["value"]
        for item in node_argument(node, "mappings", [])
    }
    if content not in mappings:
        raise ValueError(f"content_map key is not mapped: node {node.get('id')}")
    propagate_workflow_output(workflow_map, node, "content-out", mappings[content])
    return next_successor(node)


def workflow_split_event(current_id: int, workflow_map: WorkflowMap) -> int:
    node = workflow_map[current_id]
    has_event, event = read_workflow_input(node, "event-in")
    if not has_event:
        raise ValueError(f"split_event input is missing: node {node.get('id')}")
    if not isinstance(event, dict):
        raise ValueError(f"split_event input must be an event object: node {node.get('id')}")
    event_type = event.get("event_type")
    if not isinstance(event_type, str) or not event_type or "payload" not in event:
        raise ValueError(f"split_event input contains an invalid event: node {node.get('id')}")
    propagate_workflow_output(workflow_map, node, "type-out", event_type)
    propagate_workflow_output(workflow_map, node, "payload-out", _json_content(event["payload"]))
    return next_successor(node)


def _json_content(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _is_message(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and set(value) == {"role", "content"}
        and value.get("role") in {"system", "user", "assistant", "tool"}
        and isinstance(value.get("content"), str)
    )


def _is_event(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and isinstance(value.get("event_type"), str)
        and bool(value["event_type"])
        and "payload" in value
    )


def _deserialize_json_value(value: Any, value_type: str) -> Any:
    if value_type == "content":
        return _json_content(value)
    if value_type == "list-content" and isinstance(value, list):
        return [_json_content(item) for item in value]
    if value_type == "message" and _is_message(value):
        return value
    if value_type == "event" and _is_event(value):
        return value
    if value_type == "list-message" and isinstance(value, list) and all(_is_message(item) for item in value):
        return value
    if value_type == "event-list" and isinstance(value, list) and all(_is_event(item) for item in value):
        return value
    raise ValueError(f"value does not match declared type {value_type}")


def workflow_deserialize_json(current_id: int, workflow_map: WorkflowMap) -> int:
    node = workflow_map[current_id]
    has_content, content = read_workflow_input(node, "content-in")
    if not has_content:
        raise ValueError(f"deserialize_json input is missing: node {node.get('id')}")
    if not isinstance(content, str):
        raise ValueError(f"deserialize_json input must be content: node {node.get('id')}")
    try:
        document = json.loads(content)
    except json.JSONDecodeError as error:
        raise ValueError(f"deserialize_json input is invalid JSON: node {node.get('id')}") from error
    if not isinstance(document, dict):
        raise ValueError(f"deserialize_json root must be an object: node {node.get('id')}")

    converted = {}
    for output in node_argument(node, "outputs", []):
        key = output["key"]
        if key not in document:
            raise ValueError(f"deserialize_json key is missing: node {node.get('id')}, key {key}")
        try:
            converted[key] = _deserialize_json_value(document[key], output["type"])
        except ValueError as error:
            raise ValueError(
                f"deserialize_json value type mismatch: node {node.get('id')}, key {key}"
            ) from error

    for key, value in converted.items():
        propagate_workflow_output(workflow_map, node, key, value)
    return next_successor(node)


def workflow_construct_list(current_id: int, workflow_map: WorkflowMap) -> int:
    node = workflow_map[current_id]
    values = []
    item_type = node_argument(node, "item_type")
    initial_value_count = node_argument(node, "initial_value_count", 0)
    for input_index in range(initial_value_count):
        port_id = f"{item_type}-in-{input_index}"
        has_value, value = read_workflow_input(node, port_id)
        if has_value:
            values.append(value)
    propagate_workflow_output(workflow_map, node, "list-out", values)
    return next_successor(node)


def workflow_list_append(current_id: int, workflow_map: WorkflowMap) -> int:
    node = workflow_map[current_id]
    has_list, input_list = read_workflow_input(node, "list-in")
    has_item, item = read_workflow_input(node, "item-in")
    if not has_list:
        raise ValueError(f"list_append list input is missing: node {node.get('id')}")
    if not isinstance(input_list, list):
        raise ValueError(f"list_append input must be a list: node {node.get('id')}")
    if not has_item:
        raise ValueError(f"list_append item input is missing: node {node.get('id')}")
    output = [item, *input_list] if node_argument(node, "position") == "start" else [*input_list, item]
    propagate_workflow_output(workflow_map, node, "list-out", output)
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


def workflow_history(current_id: int, workflow_map: WorkflowMap) -> int:
    from history_repository import get_recent_history

    node = workflow_map[current_id]
    events = get_recent_history(
        limit=node_argument(node, "limit"),
        event_types=node_argument(node, "event_types"),
    )
    propagate_workflow_output(workflow_map, node, "events", events)
    return next_successor(node)


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


def _context_input(node: dict[str, Any], port_id: str, label: str) -> Any:
    has_value, value = read_workflow_input(node, port_id)
    if not has_value:
        raise ValueError(f"{label}: node {node.get('id')}")
    return value


def workflow_context_create(current_id: int, workflow_map: WorkflowMap) -> int:
    from workflow_context_repository import create_context

    node = workflow_map[current_id]
    value = _context_input(node, "initial-value", "Context Value 输入缺失")
    context_id = create_context(
        node["_workflow_invocation_id"], node_argument(node, "value_type"), value
    )
    node["_workflow_context_ids"].add(context_id)
    propagate_workflow_output(workflow_map, node, "context-id", context_id)
    return next_successor(node)


def workflow_context_read(current_id: int, workflow_map: WorkflowMap) -> int:
    from workflow_context_repository import read_context

    node = workflow_map[current_id]
    context_id = _context_input(node, "context-id", "Context ID 输入无效")
    value = read_context(
        context_id, node["_workflow_invocation_id"], node_argument(node, "value_type")
    )
    propagate_workflow_output(workflow_map, node, "value-out", value)
    return next_successor(node)


def workflow_context_write(current_id: int, workflow_map: WorkflowMap) -> int:
    from workflow_context_repository import write_context

    node = workflow_map[current_id]
    context_id = _context_input(node, "context-id", "Context ID 输入无效")
    value = _context_input(node, "value-in", "Context Value 输入缺失")
    write_context(
        context_id,
        node["_workflow_invocation_id"],
        node_argument(node, "value_type"),
        value,
    )
    propagate_workflow_output(workflow_map, node, "context-id", context_id)
    propagate_workflow_output(workflow_map, node, "value-out", value)
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
    "content_map": workflow_content_map,
    "split_event": workflow_split_event,
    "deserialize_json": workflow_deserialize_json,
    "construct_list": workflow_construct_list,
    "list_append": workflow_list_append,
    "foreach": workflow_foreach,
    "history": workflow_history,
    "llm": workflow_llm,
    "local_tool": workflow_local_tool,
    "remote_sync_tool": workflow_remote_sync_tool,
    "remote_async_tool": workflow_remote_async_tool,
    "context_create": workflow_context_create,
    "context_read": workflow_context_read,
    "context_write": workflow_context_write,
    "workflow": workflow_workflow,
}