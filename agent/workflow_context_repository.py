"""Store typed Workflow Context values in Redis."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import redis

from queue_client import get_connection


CONTEXT_VALUE_TYPES = {"content", "message", "list-content", "list-message"}


class WorkflowContextError(ValueError):
    """Raised when a Workflow Context operation cannot be completed."""


def _is_message(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and set(value) == {"role", "content"}
        and value.get("role") in {"system", "user", "assistant", "tool"}
        and isinstance(value.get("content"), str)
    )


def _valid_value(value_type: str, value: Any) -> bool:
    if value_type == "content":
        return isinstance(value, str)
    if value_type == "message":
        return _is_message(value)
    if value_type == "list-content":
        return isinstance(value, list) and all(isinstance(item, str) for item in value)
    if value_type == "list-message":
        return isinstance(value, list) and all(_is_message(item) for item in value)
    return False


def _ttl_seconds() -> int:
    return int(os.getenv("WORKFLOW_CONTEXT_TTL_SECONDS", "86400"))


def _max_value_bytes() -> int:
    return int(os.getenv("WORKFLOW_CONTEXT_MAX_VALUE_BYTES", "1048576"))


def _key(context_id: str) -> str:
    return f"workflow-context:{context_id}"


def _serialize(value_type: str, value: Any) -> str:
    if value_type not in CONTEXT_VALUE_TYPES or not _valid_value(value_type, value):
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


def create_context(invocation_id: str, value_type: str, value: Any) -> str:
    serialized = _serialize(value_type, value)
    context_id = f"ctx_{uuid4().hex}"
    key = _key(context_id)
    now = datetime.now(timezone.utc).isoformat()
    try:
        pipeline = get_connection().pipeline(transaction=True)
        pipeline.hset(
            key,
            mapping={
                "version": "1",
                "value_type": value_type,
                "value": serialized,
                "invocation_id": invocation_id,
                "created_at": now,
                "updated_at": now,
            },
        )
        pipeline.expire(key, _ttl_seconds())
        pipeline.execute()
    except redis.RedisError as error:
        raise WorkflowContextError("Context 存储操作失败") from error
    return context_id


def read_context(context_id: Any, invocation_id: str, value_type: str) -> Any:
    context_id = _validate_context_id(context_id)
    key = _key(context_id)
    client = get_connection()
    while True:
        try:
            with client.pipeline() as pipeline:
                pipeline.watch(key)
                stored = pipeline.hgetall(key)
                if not stored or stored.get("invocation_id") != invocation_id:
                    raise WorkflowContextError("Workflow Context 不存在")
                if stored.get("value_type") != value_type:
                    raise WorkflowContextError("Workflow Context 类型不匹配")
                try:
                    value = json.loads(stored["value"])
                except (KeyError, TypeError, json.JSONDecodeError) as error:
                    raise WorkflowContextError("Workflow Context Value 无效") from error
                if not _valid_value(value_type, value):
                    raise WorkflowContextError("Workflow Context Value 无效")
                pipeline.multi()
                pipeline.expire(key, _ttl_seconds())
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
) -> None:
    context_id = _validate_context_id(context_id)
    serialized = _serialize(value_type, value)
    key = _key(context_id)
    client = get_connection()
    while True:
        try:
            with client.pipeline() as pipeline:
                pipeline.watch(key)
                stored = pipeline.hgetall(key)
                if not stored or stored.get("invocation_id") != invocation_id:
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
                pipeline.expire(key, _ttl_seconds())
                pipeline.execute()
                return
        except redis.WatchError:
            continue
        except redis.RedisError as error:
            raise WorkflowContextError("Context 存储操作失败") from error