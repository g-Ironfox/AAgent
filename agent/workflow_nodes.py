"""Execute parsed workflow nodes synchronously."""

from __future__ import annotations

import json
import copy
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Callable
from uuid import uuid4

from workflow_contract import node_argument, tool_parameter_names


WorkflowMap = list[dict[str, Any]]
NodeHandler = Callable[[int, WorkflowMap], int]
WORKFLOW_END = -1
WORKFLOW_TIMEOUT_SECONDS = 180
logger = logging.getLogger("aagent.workflow")


def _is_map_content(value: Any) -> bool:
    return isinstance(value, dict) and all(
        isinstance(key, str) and bool(key) and isinstance(item, str)
        for key, item in value.items()
    )


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
        target_slot[2] = copy.deepcopy(value)


def _struct_defs(node: dict[str, Any]) -> dict[str, Any]:
    return node.get("_struct_definitions", {})


def workflow_construct_struct(current_id: int, workflow_map: WorkflowMap) -> int:
    from workflow_structs import validate_value
    node = workflow_map[current_id]
    sid = node_argument(node, "struct_id")
    value = {}
    for field in _struct_defs(node)[sid]["fields"]:
        present, item = read_workflow_input(node, field["name"])
        if not present:
            if field["required"]: raise ValueError(f"construct_struct missing required field {field['name']}: node {node.get('id')}")
            continue
        value[field["name"]] = item
    value = validate_value(f"struct:{sid}", value, _struct_defs(node), copy_value=True)
    propagate_workflow_output(workflow_map, node, "struct-out", value)
    return next_successor(node)


def workflow_struct_get(current_id: int, workflow_map: WorkflowMap) -> int:
    from workflow_structs import validate_value
    node = workflow_map[current_id]
    sid, name = node_argument(node, "struct_id"), node_argument(node, "field")
    definition = _struct_defs(node)[sid]
    field = next(f for f in definition["fields"] if f["name"] == name)
    present, source = read_workflow_input(node, "struct-in")
    if not present: raise ValueError(f"struct_get input missing: node {node.get('id')}")
    source = validate_value(f"struct:{sid}", source, _struct_defs(node))
    if name not in source:
        if node_argument(node, "missing", "error") != "fallback":
            raise ValueError(f"struct_get field missing: {name}, node {node.get('id')}")
        present, result = read_workflow_input(node, "fallback-in")
        if not present: raise ValueError(f"struct_get fallback missing: node {node.get('id')}")
        result = validate_value(field["type"], result, _struct_defs(node), "fallback")
    else: result = source[name]
    propagate_workflow_output(workflow_map, node, "value-out", copy.deepcopy(result))
    return next_successor(node)


def workflow_struct_update(current_id: int, workflow_map: WorkflowMap) -> int:
    from workflow_structs import validate_value
    node = workflow_map[current_id]
    sid, defs = node_argument(node, "struct_id"), _struct_defs(node)
    present, original = read_workflow_input(node, "struct-in")
    if not present: raise ValueError(f"struct_update input missing: node {node.get('id')}")
    value = validate_value(f"struct:{sid}", original, defs, copy_value=True)
    for name in node_argument(node, "remove_fields", []): value.pop(name, None)
    for name in node_argument(node, "updates", []):
        present, item = read_workflow_input(node, name)
        if present: value[name] = item
    value = validate_value(f"struct:{sid}", value, defs, copy_value=True)
    propagate_workflow_output(workflow_map, node, "struct-out", value)
    return next_successor(node)


def workflow_struct_to_json(current_id: int, workflow_map: WorkflowMap) -> int:
    from workflow_structs import validate_value
    node = workflow_map[current_id]
    present, value = read_workflow_input(node, "value-in")
    if not present: raise ValueError(f"struct_to_json input missing: node {node.get('id')}")
    value = validate_value(node_argument(node, "value_type"), value, _struct_defs(node))
    propagate_workflow_output(workflow_map, node, "content-out", json.dumps(value, ensure_ascii=False, separators=(",", ":")))
    return next_successor(node)


def workflow_json_to_struct(current_id: int, workflow_map: WorkflowMap) -> int:
    from workflow_structs import validate_value
    node = workflow_map[current_id]
    present, content = read_workflow_input(node, "content-in")
    if not present or not isinstance(content, str): raise ValueError(f"json_to_struct content input invalid: node {node.get('id')}")
    try: value = json.loads(content)
    except json.JSONDecodeError as error: raise ValueError(f"json_to_struct invalid JSON: node {node.get('id')}") from error
    value = validate_value(node_argument(node, "value_type"), value, _struct_defs(node), copy_value=True)
    propagate_workflow_output(workflow_map, node, "value-out", value)
    return next_successor(node)


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
    started_at = time.monotonic()
    started_at_utc = datetime.now(timezone.utc)
    node_trace: list[dict[str, Any]] = []
    for node in workflow_map:
        node["_workflow_invocation_id"] = invocation_id
        node["_workflow_context_ids"] = context_ids
    input_node = workflow_map[start]
    workflow_inputs: dict[str, Any] = copy.deepcopy(input_node.get("_workflow_input_values", {}))
    for port in input_node.get("workflowPorts", []):
        if port["name"] in workflow_inputs:
            continue
        targets = input_node.get("data_outputs", {}).get(port["id"], [])
        if not targets:
            workflow_inputs[port["name"]] = None
            continue
        target_id, target_port = targets[0]
        slot = workflow_map[target_id].get("data_inputs", {}).get(target_port)
        workflow_inputs[port["name"]] = copy.deepcopy(slot[2]) if isinstance(slot, list) and len(slot) == 3 else None

    def record_run(status: str, output: dict[str, Any], error: str | None = None) -> None:
        call_stack = input_node.get("_workflow_call_stack", [])
        workflow_name = call_stack[-1] if call_stack else input_node.get("_workflow_name")
        if not workflow_name:
            return
        try:
            from workflow_run_repository import record_workflow_run

            record_workflow_run({
                "run_id": invocation_id,
                "workflow_name": workflow_name,
                "call_stack": call_stack,
                "started_at": started_at_utc,
                "finished_at": datetime.now(timezone.utc),
                "duration_ms": round((time.monotonic() - started_at) * 1000),
                "status": status,
                "input": workflow_inputs,
                "output": output,
                "node_trace": node_trace,
                "error": error,
            })
        except Exception:
            logger.exception("failed to record workflow run: %s", invocation_id)

    try:
        current_id = start
        result: dict[str, Any] | None = None
        while current_id != WORKFLOW_END:
            elapsed = time.monotonic() - started_at
            if elapsed > WORKFLOW_TIMEOUT_SECONDS:
                raise TimeoutError(
                    f"workflow execution exceeded {WORKFLOW_TIMEOUT_SECONDS} seconds"
                )
            node = workflow_map[current_id]
            handler = nodes_map.get(node.get("type"))
            node_started_at = datetime.now(timezone.utc)
            node_started_monotonic = time.monotonic()
            trace_entry = {
                "index": len(node_trace) + 1,
                "node_id": node.get("id"),
                "node_name": node.get("name"),
                "node_type": node.get("type"),
                "started_at": node_started_at,
                "status": "completed",
            }
            try:
                if handler is None:
                    raise ValueError(f"unsupported workflow node type: {node.get('type')}")
                current_id = handler(current_id, workflow_map)
            except Exception as error:
                trace_entry["status"] = "failed"
                trace_entry["error"] = str(error)
                raise
            finally:
                trace_entry["finished_at"] = datetime.now(timezone.utc)
                trace_entry["duration_ms"] = round(
                    (time.monotonic() - node_started_monotonic) * 1000
                )
                node_trace.append(trace_entry)
            node_result = node.pop("_workflow_result", None)
            if isinstance(node_result, dict):
                result = node_result
        result = result or {}
        record_run("completed", result)
        return result
    except Exception as error:
        record_run("failed", {}, str(error))
        raise
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

    from llm import chat_with_model
    from tools.tool import registered_tools

    dynamic_tools_slot = node.get("data_inputs", {}).get("available-tools-in")
    has_dynamic_tools = (
        isinstance(dynamic_tools_slot, list)
        and len(dynamic_tools_slot) == 3
        and dynamic_tools_slot[0] is not None
    )
    dynamic_tool_names = dynamic_tools_slot[2] if has_dynamic_tools else None
    metadata_tools = node.get("_metadata_tools", [])
    if not metadata_tools and node.get("_metadata_local_tool_names"):
        metadata_tools = [
            {"name": name, "kind": "local"}
            for name in node["_metadata_local_tool_names"]
        ]
    metadata_by_name = {tool["name"]: tool.get("kind", "remote") for tool in metadata_tools}
    if has_dynamic_tools:
        if not isinstance(dynamic_tool_names, list) or any(
            not isinstance(name, str) or not name.strip() for name in dynamic_tool_names
        ):
            raise ValueError(f"llm available-tools-in must be a list of non-empty tool names: node {node.get('id')}")
        configured_tools = list(dict.fromkeys(name.strip() for name in dynamic_tool_names))
        invalid_names = sorted(set(configured_tools) - metadata_by_name.keys())
        if invalid_names:
            raise ValueError(f"llm tools must reference metadata.tools declarations: {', '.join(invalid_names)}")
    else:
        configured_tools = node_argument(node, "tools", []) or [tool["name"] for tool in metadata_tools]
        invalid_names = sorted(set(configured_tools) - metadata_by_name.keys())
        if invalid_names:
            raise ValueError(f"llm tools must reference metadata.tools declarations: {', '.join(invalid_names)}")

    registered_by_name = {schema["function"]["name"]: schema for schema in registered_tools}
    selected_local = {name for name in configured_tools if metadata_by_name.get(name) == "local"}
    missing_local = sorted(selected_local - registered_by_name.keys())
    if missing_local:
        raise ValueError(f"local tool schemas are not registered: {', '.join(missing_local)}")
    tools = [registered_by_name[name] for name in configured_tools if name in selected_local]
    selected_remote = {name for name in configured_tools if metadata_by_name.get(name) == "remote"}
    if selected_remote:
        from tool_server_client import ToolServerError, get_remote_tool_schemas

        try:
            tools.extend(get_remote_tool_schemas(selected_remote))
        except ToolServerError as error:
            raise ValueError(f"llm could not load Remote Tool schemas: {error}") from error
    content, reasoning, tool_calls = chat_with_model(
        messages,
        node_argument(node, "model"),
        tools=tools,
        think=node_argument(node, "think", False),
    )
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


def workflow_construct_map_content(current_id: int, workflow_map: WorkflowMap) -> int:
    node = workflow_map[current_id]
    mappings = {}
    for item in node_argument(node, "mappings", []):
        if item.get("value_source", "fixed") == "port":
            has_value, value = read_workflow_input(node, item["port_id"])
            if not has_value:
                raise ValueError(
                    f"construct_map_content value input is missing: node {node.get('id')}, port {item['port_id']}"
                )
            if not isinstance(value, str):
                raise ValueError(
                    f"construct_map_content value input must be content: node {node.get('id')}, port {item['port_id']}"
                )
        else:
            value = item["value"]
        mappings[item["key"]] = value
    propagate_workflow_output(workflow_map, node, "map-out", mappings)
    return next_successor(node)


def workflow_map_content_get(current_id: int, workflow_map: WorkflowMap) -> int:
    node = workflow_map[current_id]
    has_mapping, mapping = read_workflow_input(node, "map-in")
    has_key, key = read_workflow_input(node, "key-in")
    if not has_mapping:
        raise ValueError(f"map_content_get Map input is missing: node {node.get('id')}")
    if not isinstance(mapping, dict) or any(
        not isinstance(map_key, str) or not map_key or not isinstance(value, str)
        for map_key, value in mapping.items()
    ):
        raise ValueError(f"map_content_get input must be map-content: node {node.get('id')}")
    if not has_key:
        raise ValueError(f"map_content_get key input is missing: node {node.get('id')}")
    if not isinstance(key, str):
        raise ValueError(f"map_content_get key input must be content: node {node.get('id')}")
    if key not in mapping:
        raise ValueError(f"map_content_get key is not mapped: node {node.get('id')}")
    propagate_workflow_output(workflow_map, node, "content-out", mapping[key])
    return next_successor(node)


def workflow_construct_event(current_id: int, workflow_map: WorkflowMap) -> int:
    node = workflow_map[current_id]
    event_type = node_argument(node, "event_type")
    if not isinstance(event_type, str) or not event_type.strip():
        raise ValueError(f"construct_event event_type is invalid: node {node.get('id')}")
    has_payload, payload_content = read_workflow_input(node, "payload-in")
    if not has_payload or not isinstance(payload_content, str):
        raise ValueError(f"construct_event payload input must be content: node {node.get('id')}")
    try:
        payload = json.loads(payload_content)
    except json.JSONDecodeError as error:
        raise ValueError(f"construct_event payload is invalid JSON: node {node.get('id')}") from error
    if not isinstance(payload, dict):
        raise ValueError(f"construct_event payload must be an object: node {node.get('id')}")
    propagate_workflow_output(
        workflow_map,
        node,
        "event-out",
        {"version": "1.1", "event_type": event_type, "payload": payload},
    )
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


def workflow_publish_event(current_id: int, workflow_map: WorkflowMap) -> int:
    node = workflow_map[current_id]
    has_event, event = read_workflow_input(node, "event-in")
    if not has_event:
        raise ValueError(f"publish_event input is missing: node {node.get('id')}")
    if (
        not isinstance(event, dict)
        or event.get("version") != "1.1"
        or not isinstance(event.get("event_type"), str)
        or not event["event_type"]
        or not isinstance(event.get("payload"), dict)
    ):
        raise ValueError(f"publish_event input contains an invalid event: node {node.get('id')}")
    from queue_client import MAIN_AGENT_QUEUE_NAME, publish_to_queue

    publish_to_queue(MAIN_AGENT_QUEUE_NAME, event)
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
    if value_type == "list-event" and isinstance(value, list) and all(_is_event(item) for item in value):
        return value
    if value_type == "map-content" and _is_map_content(value):
        return dict(value)
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
    branch_key = f"branch-{key}"
    if branch_key not in node.get("successors", {}):
        branch_key = "branch$others"
    return next_successor(node, branch_key)


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


def workflow_tool(current_id: int, workflow_map: WorkflowMap) -> int:
    node = workflow_map[current_id]
    if node_argument(node, "mode", "sync") != "sync":
        raise ValueError("tool only supports sync mode; use remote_async_tool")
    kind = node.get("_tool_kind")
    if kind == "local":
        if node_argument(node, "mode", "sync") != "sync":
            raise ValueError("local tool only supports sync mode")
        return workflow_local_tool(current_id, workflow_map)
    if kind == "remote":
        return workflow_remote_sync_tool(current_id, workflow_map)
    raise ValueError("tool kind must be resolved from metadata.tools")


def workflow_local_tool(current_id: int, workflow_map: WorkflowMap) -> int:
    from tools.tool import execute_tool

    node = workflow_map[current_id]
    result = execute_tool(
        node["id"], node_argument(node, "tool"), _tool_arguments(node), preserve_result=True
    )
    if node.get("type") == "local_tool":
        propagate_workflow_output(workflow_map, node, "output", _tool_output(result))
        return next_successor(node)

    outputs = node_argument(node, "outputs", [])
    if isinstance(result, dict):
        if len(outputs) == 1 and outputs[0]["name"] == "output" and "output" not in result:
            values = {"output": result}
        else:
            missing = [output["name"] for output in outputs if output["name"] not in result]
            if missing:
                raise ValueError(f"local tool result is missing outputs: {', '.join(missing)}")
            values = result
    elif len(outputs) == 1:
        values = {outputs[0]["name"]: result}
    elif outputs:
        raise ValueError("local tool result must be an object for named outputs")
    else:
        values = {}

    for output in outputs:
        name = output["name"]
        value = values[name]
        if output["type"] == "content":
            value = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
        elif output["type"] == "map-content" and not _is_map_content(value):
            raise ValueError(f"local tool output {name} must match map-content")
        propagate_workflow_output(workflow_map, node, name, value)
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
        if outputs[0]["type"] == "map-content" and not _is_map_content(result):
            raise ValueError("remote sync tool result must match map-content")
        propagate_workflow_output(workflow_map, node, "result", result)
    elif isinstance(result, dict):
        missing = [output["name"] for output in outputs if output["name"] not in result]
        if missing:
            raise ValueError(f"remote sync tool result is missing outputs: {', '.join(missing)}")
        for output in outputs:
            value = result[output["name"]]
            if output["type"] == "map-content" and not _is_map_content(value):
                raise ValueError(f"remote sync tool output {output['name']} must match map-content")
            propagate_workflow_output(workflow_map, node, output["name"], value)
    elif outputs:
        raise ValueError("remote sync tool result must be an object for named outputs")
    return next_successor(node)


def workflow_json_tool(current_id: int, workflow_map: WorkflowMap) -> int:
    node = workflow_map[current_id]
    tool_name = None
    try:
        has_name, tool_name = read_workflow_input(node, "tool-name")
        has_arguments, arguments_json = read_workflow_input(node, "arguments-json")
        if not has_name or not isinstance(tool_name, str) or not tool_name.strip():
            raise ValueError(f"JSON Tool name is missing: node {node.get('id')}")
        if not has_arguments or not isinstance(arguments_json, str):
            raise ValueError(f"JSON Tool arguments are missing: node {node.get('id')}")
        arguments = json.loads(arguments_json)
        if not isinstance(arguments, dict):
            raise ValueError(f"JSON Tool arguments must be a JSON object: node {node.get('id')}")

        from tools.tool import execute_tool, tool_handlers

        name = tool_name.strip()
        if name in tool_handlers:
            result = execute_tool(node["id"], name, arguments, preserve_result=True)
        else:
            from tool_server_client import call_remote_tool

            timeout_ms = int(os.getenv("TOOL_CLIENT_DEFAULT_WAIT_MS", "10000"))
            result = call_remote_tool(name, arguments, "wait", timeout_ms, None)

        result_json = json.dumps(result, ensure_ascii=False, separators=(",", ":"), default=str)
    except Exception as error:
        details = {
            "tool": tool_name.strip() if isinstance(tool_name, str) else None,
            "error": {"type": type(error).__name__, "message": str(error)},
        }
        task_id = getattr(error, "task_id", None)
        if task_id:
            details["error"]["task_id"] = task_id
        error_json = json.dumps(details, ensure_ascii=False, separators=(",", ":"))
        propagate_workflow_output(workflow_map, node, "error-json", error_json)
        if isinstance(node.get("successors", {}).get("error"), int):
            logger.warning("JSON Tool routed an error: node=%s, tool=%s, error=%s", node.get("id"), details["tool"], str(error))
            return next_successor(node, "error")
        raise

    propagate_workflow_output(workflow_map, node, "result-json", result_json)
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
        node["_workflow_invocation_id"],
        node_argument(node, "value_type"),
        value,
        node_argument(node, "context_id") or None,
        _struct_defs(node),
    )
    node["_workflow_context_ids"].add(context_id)
    propagate_workflow_output(workflow_map, node, "context-id", context_id)
    return next_successor(node)


def workflow_context_read(current_id: int, workflow_map: WorkflowMap) -> int:
    from workflow_context_repository import read_context

    node = workflow_map[current_id]
    context_id = node_argument(node, "context_id") if node_argument(node, "context_id_source", "port") == "fixed" else _context_input(node, "context-id", "Context ID 输入无效")
    value = read_context(
        context_id, node["_workflow_invocation_id"], node_argument(node, "value_type"), _struct_defs(node)
    )
    propagate_workflow_output(workflow_map, node, "value-out", value)
    return next_successor(node)


def workflow_context_write(current_id: int, workflow_map: WorkflowMap) -> int:
    from workflow_context_repository import write_context

    node = workflow_map[current_id]
    context_id = node_argument(node, "context_id") if node_argument(node, "context_id_source", "port") == "fixed" else _context_input(node, "context-id", "Context ID 输入无效")
    value = _context_input(node, "value-in", "Context Value 输入缺失")
    write_context(
        context_id,
        node["_workflow_invocation_id"],
        node_argument(node, "value_type"),
        value,
        _struct_defs(node),
    )
    propagate_workflow_output(workflow_map, node, "context-id", context_id)
    propagate_workflow_output(workflow_map, node, "value-out", value)
    return next_successor(node)


def workflow_session_create(current_id: int, workflow_map: WorkflowMap) -> int:
    from workflow_session_repository import create_session

    node = workflow_map[current_id]
    value = _context_input(node, "initial-value", "Session Value 输入缺失")
    session_id = create_session(node_argument(node, "value_type"), value)["id"]
    propagate_workflow_output(workflow_map, node, "session-id", session_id)
    return next_successor(node)


def workflow_session_read(current_id: int, workflow_map: WorkflowMap) -> int:
    from workflow_session_repository import read_session

    node = workflow_map[current_id]
    session_id = _context_input(node, "session-id", "Session ID 输入无效")
    value = read_session(session_id, node_argument(node, "value_type"))
    propagate_workflow_output(workflow_map, node, "value-out", value)
    return next_successor(node)


def workflow_session_write(current_id: int, workflow_map: WorkflowMap) -> int:
    from workflow_session_repository import write_session

    node = workflow_map[current_id]
    session_id = _context_input(node, "session-id", "Session ID 输入无效")
    value = _context_input(node, "value-in", "Session Value 输入缺失")
    write_session(session_id, node_argument(node, "value_type"), value)
    propagate_workflow_output(workflow_map, node, "session-id", session_id)
    propagate_workflow_output(workflow_map, node, "value-out", value)
    return next_successor(node)


def workflow_workflow(current_id: int, workflow_map: WorkflowMap) -> int:
    from workflow_parser import _read_workspace_workflow_by_name, parse_workflow
    from workflow_validator import validate_workflow

    parent_node = workflow_map[current_id]
    workflow_name = node_argument(parent_node, "workflow_name")
    call_stack = parent_node.get("_workflow_call_stack", [])
    if workflow_name in call_stack:
        chain = " -> ".join([*call_stack, workflow_name])
        raise ValueError(f"recursive workflow call detected: {chain}")

    workflow_document = _read_workspace_workflow_by_name(workflow_name)
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
    child_inputs: dict[str, Any] = {}
    for port in child_input.get("workflowPorts", []):
        has_value, value = read_workflow_input(
            parent_node, f"workflow:{port['name']}"
        )
        child_inputs[port["name"]] = value if has_value else None
        if has_value:
            propagate_workflow_output(child_map, child_input, port["id"], value)
    child_input["_workflow_input_values"] = child_inputs

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
    "construct_map_content": workflow_construct_map_content,
    "construct_struct": workflow_construct_struct,
    "struct_get": workflow_struct_get,
    "struct_update": workflow_struct_update,
    "struct_to_json": workflow_struct_to_json,
    "json_to_struct": workflow_json_to_struct,
    "map_content_get": workflow_map_content_get,
    "construct_event": workflow_construct_event,
    "split_event": workflow_split_event,
    "publish_event": workflow_publish_event,
    "deserialize_json": workflow_deserialize_json,
    "construct_list": workflow_construct_list,
    "list_append": workflow_list_append,
    "foreach": workflow_foreach,
    "history": workflow_history,
    "llm": workflow_llm,
    "tool": workflow_tool,
    "json_tool": workflow_json_tool,
    "local_tool": workflow_local_tool,
    "remote_sync_tool": workflow_remote_sync_tool,
    "remote_async_tool": workflow_remote_async_tool,
    "context_create": workflow_context_create,
    "context_read": workflow_context_read,
    "context_write": workflow_context_write,
    "session_create": workflow_session_create,
    "session_read": workflow_session_read,
    "session_write": workflow_session_write,
    "workflow": workflow_workflow,
}
