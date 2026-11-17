from __future__ import annotations

import json
import re
import base64
import binascii
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from pymongo import ReturnDocument
from pymongo.collection import Collection
from pymongo.errors import PyMongoError

from workflow_contract import is_number_value

MAX_VALUE_BYTES = 1024 * 1024
SESSION_ID_PATTERN = re.compile(r"^ses_[0-9a-f]{32}$")
SESSION_VALUE_TYPES = {"content", "number", "message", "event", "map-content", "list-content", "list-message", "list-event"}


def valid_value(value_type: str, value: Any) -> bool:
    def message(item: Any) -> bool:
        return isinstance(item, dict) and set(item) == {"role", "content"} and item["role"] in {"system", "user", "assistant", "tool"} and isinstance(item["content"], str)

    def event(item: Any) -> bool:
        return isinstance(item, dict) and isinstance(item.get("event_type"), str) and bool(item["event_type"]) and "payload" in item

    if value_type == "number":
        return is_number_value(value)
    if value_type == "content":
        return isinstance(value, str)
    if value_type == "message":
        return message(value)
    if value_type == "event":
        return event(value)
    if value_type == "map-content":
        return isinstance(value, dict) and all(
            isinstance(key, str) and bool(key) and isinstance(item, str)
            for key, item in value.items()
        )
    if value_type == "list-content":
        return isinstance(value, list) and all(isinstance(item, str) for item in value)
    if value_type == "list-message":
        return isinstance(value, list) and all(message(item) for item in value)
    if value_type == "list-event":
        return isinstance(value, list) and all(event(item) for item in value)
    return False


class SessionValueRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value_type: str
    value: Any
    updated_at: datetime | None = None


def _validate_value(value_type: str, value: Any) -> str | None:
    if value_type not in SESSION_VALUE_TYPES or not valid_value(value_type, value):
        return "Session Value 无效"
    try:
        serialized = json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError):
        return "Session Value 无效"
    if len(serialized.encode("utf-8")) > MAX_VALUE_BYTES:
        return "Session Value 过大"
    return None


def _response(document: dict[str, Any], include_value: bool = True) -> dict[str, Any]:
    result = {
        "id": document["_id"],
        "value_type": document.get("value_type"),
        "created_at": document.get("created_at"),
        "updated_at": document.get("updated_at"),
    }
    if include_value:
        result["value"] = document.get("value")
    return result


def _now() -> datetime:
    now = datetime.now(timezone.utc)
    return now.replace(microsecond=now.microsecond // 1000 * 1000)


def create_sessions_router(sessions: Collection) -> APIRouter:
    router = APIRouter(prefix="/api/sessions")

    @router.get("")
    def list_sessions(
        limit: int = Query(default=50, ge=1, le=100),
        cursor: str | None = None,
        q: str = Query(default="", max_length=100),
    ):
        query: dict[str, Any] = {}
        if q:
            query["_id"] = {"$regex": f"^{re.escape(q)}"}
        if cursor:
            try:
                timestamp, last_id = json.loads(base64.urlsafe_b64decode(cursor.encode("ascii")))
                if not isinstance(timestamp, str) or not isinstance(last_id, str):
                    raise ValueError
                last_updated = datetime.fromisoformat(timestamp)
                if not SESSION_ID_PATTERN.fullmatch(last_id) or last_updated.tzinfo is None:
                    raise ValueError
            except (ValueError, TypeError, IndexError, UnicodeError, binascii.Error):
                return JSONResponse(status_code=400, content={"error": "Session 游标无效"})
            query["$or"] = [
                {"updated_at": {"$lt": last_updated}},
                {"updated_at": last_updated, "_id": {"$lt": last_id}},
            ]
        try:
            documents = list(
                sessions.find(query, {"value": 0})
                .sort([("updated_at", -1), ("_id", -1)])
                .limit(limit + 1)
            )
        except PyMongoError:
            return JSONResponse(status_code=503, content={"error": "Session 列表暂时不可用"})
        has_more = len(documents) > limit
        items = [_response(document, include_value=False) for document in documents[:limit]]
        next_cursor = None
        if has_more and items:
            last = items[-1]
            next_cursor = base64.urlsafe_b64encode(json.dumps([last["updated_at"].isoformat(), last["id"]]).encode("utf-8")).decode("ascii")
        return {"items": items, "next_cursor": next_cursor}

    @router.get("/{session_id}")
    def get_session(session_id: str):
        try:
            document = sessions.find_one({"_id": session_id})
        except PyMongoError:
            return JSONResponse(status_code=503, content={"error": "Session 暂时不可用"})
        if document is None:
            return JSONResponse(status_code=404, content={"error": "Session 不存在或已被删除"})
        return _response(document)

    @router.post("", status_code=201)
    def create_session(payload: SessionValueRequest):
        error = _validate_value(payload.value_type, payload.value)
        if error:
            return JSONResponse(status_code=400, content={"error": error})
        now = _now()
        document = {
            "_id": f"ses_{uuid4().hex}",
            "value_type": payload.value_type,
            "value": payload.value,
            "created_at": now,
            "updated_at": now,
        }
        try:
            sessions.insert_one(document)
        except PyMongoError:
            return JSONResponse(status_code=503, content={"error": "暂时无法创建 Session"})
        return _response(document)

    @router.put("/{session_id}")
    def update_session(session_id: str, payload: SessionValueRequest):
        error = _validate_value(payload.value_type, payload.value)
        if error:
            return JSONResponse(status_code=400, content={"error": error})
        if payload.updated_at is None:
            return JSONResponse(status_code=400, content={"error": "updated_at 不能为空"})
        now = max(_now(), payload.updated_at + timedelta(milliseconds=1))
        try:
            document = sessions.find_one_and_update(
                {"_id": session_id, "value_type": payload.value_type, "updated_at": payload.updated_at},
                {"$set": {"value": payload.value, "updated_at": now}},
                return_document=ReturnDocument.AFTER,
            )
            if document is not None:
                return _response(document)
            if sessions.find_one({"_id": session_id}) is None:
                return JSONResponse(status_code=404, content={"error": "Session 不存在或已被删除"})
            return JSONResponse(status_code=409, content={"error": "Session 已被其他操作更新，请刷新后重试"})
        except PyMongoError:
            return JSONResponse(status_code=503, content={"error": "暂时无法保存 Session"})

    @router.delete("/{session_id}")
    def delete_session(session_id: str):
        try:
            result = sessions.delete_one({"_id": session_id})
        except PyMongoError:
            return JSONResponse(status_code=503, content={"error": "暂时无法删除 Session"})
        if result.deleted_count == 0:
            return JSONResponse(status_code=404, content={"error": "Session 不存在或已被删除"})
        return {"deleted": True, "id": session_id}

    return router
