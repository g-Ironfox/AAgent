"""Store globally accessible typed Workflow Session values in MongoDB."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from workflow_contract import is_number_value
from uuid import uuid4

from pymongo import MongoClient
from pymongo.errors import PyMongoError


SESSION_VALUE_TYPES = {
    "content",
    "number",
    "message",
    "list-content",
    "list-message",
    "map-content",
}
SESSION_ID_PATTERN = re.compile(r"^ses_[0-9a-f]{32}$")


class WorkflowSessionError(ValueError):
    """Raised when a Workflow Session operation cannot be completed."""


_client = None
_collection = None


def _is_message(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and set(value) == {"role", "content"}
        and value.get("role") in {"system", "user", "assistant", "tool"}
        and isinstance(value.get("content"), str)
    )


def valid_value(value_type: str, value: Any) -> bool:
    if value_type == "number":
        return is_number_value(value)
    if value_type == "content":
        return isinstance(value, str)
    if value_type == "message":
        return _is_message(value)
    if value_type == "list-content":
        return isinstance(value, list) and all(isinstance(item, str) for item in value)
    if value_type == "list-message":
        return isinstance(value, list) and all(_is_message(item) for item in value)
    if value_type == "map-content":
        return isinstance(value, dict) and all(
            isinstance(key, str) and bool(key) and isinstance(item, str)
            for key, item in value.items()
        )
    return False


def _max_value_bytes() -> int:
    return int(os.getenv("WORKFLOW_SESSION_MAX_VALUE_BYTES", "1048576"))


def _serialize(value_type: str, value: Any) -> str:
    if value_type not in SESSION_VALUE_TYPES or not valid_value(value_type, value):
        raise WorkflowSessionError("Workflow Session Value 无效")
    try:
        serialized = json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as error:
        raise WorkflowSessionError("Workflow Session Value 无效") from error
    if len(serialized.encode("utf-8")) > _max_value_bytes():
        raise WorkflowSessionError("Workflow Session Value 过大")
    return serialized


def _validate_session_id(session_id: Any) -> str:
    if not isinstance(session_id, str) or not SESSION_ID_PATTERN.fullmatch(session_id):
        raise WorkflowSessionError("Session ID 输入无效")
    return session_id


def _now() -> datetime:
    now = datetime.now(timezone.utc)
    return now.replace(microsecond=now.microsecond // 1000 * 1000)


def get_session_collection():
    global _client, _collection
    if _collection is None:
        options = {
            "host": os.getenv("MONGO_HOST", "mongodb"),
            "port": int(os.getenv("MONGO_PORT", "27017")),
            "serverSelectionTimeoutMS": 5000,
            "tz_aware": True,
        }
        if os.getenv("MONGO_USER"):
            options.update(
                username=os.environ["MONGO_USER"],
                password=os.getenv("MONGO_PASS", ""),
                authSource="admin",
            )
        _client = MongoClient(**options)
        _collection = _client[
            os.getenv("MONGO_DATABASE", "agent")
        ][os.getenv("MONGO_SESSION_COLLECTION", "sessions")]
        _collection.create_index("updated_at", name="session_updated_at")
    return _collection


def _response(document: dict[str, Any]) -> dict[str, Any]:
    value_type = document.get("value_type")
    value = document.get("value")
    if not isinstance(value_type, str) or not valid_value(value_type, value):
        raise WorkflowSessionError("Workflow Session Value 无效")
    return {
        "id": document["_id"],
        "value_type": value_type,
        "value": value,
        "created_at": document.get("created_at"),
        "updated_at": document.get("updated_at"),
    }


def create_session(value_type: str, value: Any) -> dict[str, Any]:
    _serialize(value_type, value)
    now = _now()
    document = {
        "_id": f"ses_{uuid4().hex}",
        "value_type": value_type,
        "value": value,
        "created_at": now,
        "updated_at": now,
    }
    try:
        get_session_collection().insert_one(document)
    except PyMongoError as error:
        raise WorkflowSessionError("Session 存储操作失败") from error
    return _response(document)


def read_session(session_id: Any, value_type: str) -> Any:
    session_id = _validate_session_id(session_id)
    try:
        document = get_session_collection().find_one(
            {"_id": session_id, "value_type": value_type}
        )
    except PyMongoError as error:
        raise WorkflowSessionError("Session 存储操作失败") from error
    if document is None:
        raise WorkflowSessionError("Workflow Session 不存在或类型不匹配")
    return _response(document)["value"]


def write_session(session_id: Any, value_type: str, value: Any) -> None:
    session_id = _validate_session_id(session_id)
    _serialize(value_type, value)
    try:
        collection = get_session_collection()
        while True:
            document = collection.find_one({"_id": session_id, "value_type": value_type}, {"updated_at": 1})
            if document is None:
                raise WorkflowSessionError("Workflow Session 不存在或类型不匹配")
            updated_at = max(_now(), document["updated_at"] + timedelta(milliseconds=1))
            result = collection.update_one(
                {"_id": session_id, "value_type": value_type, "updated_at": document["updated_at"]},
                {"$set": {"value": value, "updated_at": updated_at}},
            )
            if result.matched_count:
                return
    except PyMongoError as error:
        raise WorkflowSessionError("Session 存储操作失败") from error
