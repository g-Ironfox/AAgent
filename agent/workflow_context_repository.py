"""Store typed Workflow Context values in Redis."""

from __future__ import annotations

import json
import os
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any

from workflow_contract import is_number_value
from uuid import uuid4

import redis

from redis_client import get_connection


CONTEXT_VALUE_TYPES = {
    "content",
    "number",
    "list-content",
    "map-content",
}


class WorkflowContextError(ValueError):
    """Raised when a Workflow Context operation cannot be completed."""


def _valid_value(value_type: str, value: Any, struct_definitions: dict[str, Any] | None = None) -> bool:
    if value_type.startswith(("struct:", "list-struct:")):
        try:
            from workflow_structs import validate_value
            validate_value(value_type, value, struct_definitions or {})
            return True
        except ValueError:
            return False
    if value_type == "number":
        return is_number_value(value)
    if value_type == "content":
        return isinstance(value, str)
    if value_type == "list-content":
        return isinstance(value, list) and all(isinstance(item, str) for item in value)
    if value_type == "map-content":
        return isinstance(value, dict) and all(
            isinstance(key, str) and bool(key) and isinstance(item, str)
            for key, item in value.items()
        )
    return False


current_persistent_invocation_id = ContextVar("persistent_workflow_invocation", default=None)


def _refresh_lifetime(pipeline, key: str, stored: dict) -> None:
    if stored.get("persistent") == "1":
        pipeline.persist(key)
    else:
        pipeline.expire(key, _ttl_seconds())


def _ttl_seconds() -> int:
    return int(os.getenv("WORKFLOW_CONTEXT_TTL_SECONDS", "86400"))


def _max_value_bytes() -> int:
    return int(os.getenv("WORKFLOW_CONTEXT_MAX_VALUE_BYTES", "1048576"))


def _key(context_id: str) -> str:
    return f"workflow-context:{context_id}"


def _serialize(value_type: str, value: Any, struct_definitions: dict[str, Any] | None = None) -> str:
    if (value_type not in CONTEXT_VALUE_TYPES and not value_type.startswith(("struct:", "list-struct:"))) or not _valid_value(value_type, value, struct_definitions):
        raise WorkflowContextError("Workflow Context Value 无效")
    serialized = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if len(serialized.encode("utf-8")) > _max_value_bytes():
        raise WorkflowContextError("Workflow Context Value 过大")
    return serialized


def _validate_context_id(context_id: Any) -> str:
    if not isinstance(context_id, str) or not context_id:
        raise WorkflowContextError("Context ID 输入无效")
    return context_id


def delete_contexts(context_ids: set[str]) -> None:
    if not context_ids:
        return
    try:
        get_connection().delete(*(_key(context_id) for context_id in context_ids))
    except redis.RedisError as error:
        raise WorkflowContextError("Context 存储操作失败") from error


def create_context(
    invocation_id: str, value_type: str, value: Any, context_id: str | None = None,
    struct_definitions: dict[str, Any] | None = None,
) -> str:
    serialized = _serialize(value_type, value, struct_definitions)
    context_id = context_id or f"ctx_{uuid4().hex}"
    context_id = _validate_context_id(context_id)
    key = _key(context_id)
    now = datetime.now(timezone.utc).isoformat()
    mapping = {
        "version": "1",
        "value_type": value_type,
        "value": serialized,
        "invocation_id": invocation_id,
        "created_at": now,
        "updated_at": now,
    }
    persistent = current_persistent_invocation_id.get() == invocation_id
    if persistent:
        mapping["persistent"] = "1"
    try:
        created = get_connection().eval(
            "if redis.call('EXISTS', KEYS[1]) == 1 then return 0 end "
            "redis.call('HSET', KEYS[1], unpack(ARGV, 1, #ARGV - 1)) "
            "if tonumber(ARGV[#ARGV]) > 0 then redis.call('EXPIRE', KEYS[1], ARGV[#ARGV]) end "
            "return 1",
            1,
            key,
            *(argument for field_value in mapping.items() for argument in field_value),
            "0" if persistent else str(_ttl_seconds()),
        )
        if not created:
            raise WorkflowContextError("Context ID 已存在")
    except redis.RedisError as error:
        raise WorkflowContextError("Context 存储操作失败") from error
    return context_id


def read_context(
    context_id: Any,
    invocation_id: str,
    value_type: str,
    struct_definitions: dict[str, Any] | None = None,
    *,
    ancestor_invocation_ids: tuple[str, ...] = (),
) -> Any:
    context_id = _validate_context_id(context_id)
    key = _key(context_id)
    client = get_connection()
    allowed_invocation_ids = {invocation_id, *ancestor_invocation_ids}
    while True:
        try:
            with client.pipeline() as pipeline:
                pipeline.watch(key)
                stored = pipeline.hgetall(key)
                if not stored or stored.get("invocation_id") not in allowed_invocation_ids:
                    raise WorkflowContextError("Workflow Context 不存在")
                if stored.get("value_type") != value_type:
                    raise WorkflowContextError("Workflow Context 类型不匹配")
                try:
                    value = json.loads(stored["value"])
                except (KeyError, TypeError, json.JSONDecodeError) as error:
                    raise WorkflowContextError("Workflow Context Value 无效") from error
                if not _valid_value(value_type, value, struct_definitions):
                    raise WorkflowContextError("Workflow Context Value 无效")
                pipeline.multi()
                _refresh_lifetime(pipeline, key, stored)
                pipeline.execute()
                return value
        except redis.WatchError:
            continue
        except redis.RedisError as error:
            raise WorkflowContextError("Context 存储操作失败") from error


def write_context(
    context_id: Any,
    invocation_id: str,
    value_type: str,
    value: Any,
    struct_definitions: dict[str, Any] | None = None,
    *,
    ancestor_invocation_ids: tuple[str, ...] = (),
) -> None:
    context_id = _validate_context_id(context_id)
    serialized = _serialize(value_type, value, struct_definitions)
    key = _key(context_id)
    client = get_connection()
    allowed_invocation_ids = {invocation_id, *ancestor_invocation_ids}
    while True:
        try:
            with client.pipeline() as pipeline:
                pipeline.watch(key)
                stored = pipeline.hgetall(key)
                if not stored or stored.get("invocation_id") not in allowed_invocation_ids:
                    raise WorkflowContextError("Workflow Context 不存在")
                if stored.get("value_type") != value_type:
                    raise WorkflowContextError("Workflow Context 类型不匹配")
                pipeline.multi()
                pipeline.hset(
                    key,
                    mapping={
                        "value": serialized,
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    },
                )
                _refresh_lifetime(pipeline, key, stored)
                pipeline.execute()
                return
        except redis.WatchError:
            continue
        except redis.RedisError as error:
            raise WorkflowContextError("Context 存储操作失败") from error


def pop_context(
    context_id: Any,
    invocation_id: str,
    value_type: str,
    position: str = "end",
    struct_definitions: dict[str, Any] | None = None,
    *,
    ancestor_invocation_ids: tuple[str, ...] = (),
) -> tuple[bool, Any]:
    """Atomically remove one list item; an empty list returns (False, None)."""
    context_id = _validate_context_id(context_id)
    if not isinstance(value_type, str) or not value_type.startswith("list-"):
        raise WorkflowContextError("while_pop Context 类型必须为列表")
    if position not in {"start", "end"}:
        raise WorkflowContextError("while_pop position must be 'start' or 'end'")
    key = _key(context_id)
    client = get_connection()
    allowed_invocation_ids = {invocation_id, *ancestor_invocation_ids}
    while True:
        try:
            with client.pipeline() as pipeline:
                pipeline.watch(key)
                stored = pipeline.hgetall(key)
                if not stored or stored.get("invocation_id") not in allowed_invocation_ids:
                    raise WorkflowContextError("Workflow Context 不存在")
                if stored.get("value_type") != value_type:
                    raise WorkflowContextError("Workflow Context 类型不匹配")
                try:
                    items = json.loads(stored["value"])
                except (KeyError, TypeError, json.JSONDecodeError) as error:
                    raise WorkflowContextError("Workflow Context Value 无效") from error
                if not _valid_value(value_type, items, struct_definitions):
                    raise WorkflowContextError("Workflow Context Value 无效")
                has_item = bool(items)
                item = items.pop(0 if position == "start" else -1) if has_item else None
                serialized = _serialize(value_type, items, struct_definitions) if has_item else None
                pipeline.multi()
                if has_item:
                    pipeline.hset(key, mapping={
                        "value": serialized,
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    })
                _refresh_lifetime(pipeline, key, stored)
                pipeline.execute()
                return has_item, item
        except redis.WatchError:
            continue
        except redis.RedisError as error:
            raise WorkflowContextError("Context 存储操作失败") from error
