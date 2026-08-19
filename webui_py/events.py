import json
import uuid
from datetime import datetime, timezone
from typing import Any

import redis
from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from pymongo import DESCENDING
from pymongo.collection import Collection
from pymongo.errors import PyMongoError

from common import limit_error

MAX_TERMINAL_RUNES = 4000
MAX_EVENT_BODY_BYTES = 256 * 1024


class TerminalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str
    files: list[str] = Field(default_factory=list)


class DeleteEventRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str
    doc_id: str | None = None
    position: int | None = None
    fingerprint: str | None = None


class UpdateEventRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str
    event: dict[str, Any]
    doc_id: str | None = None
    position: int | None = None
    fingerprint: str | None = None


def event_fingerprint(event: dict[str, Any]) -> str:
    encoded = json.dumps(event, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    value = 1469598103934665603
    for byte in encoded:
        value ^= byte
        value = (value * 1099511628211) & 0xFFFFFFFFFFFFFFFF
    alphabet = "0123456789abcdefghijklmnopqrstuvwxyz"
    if value == 0:
        return "0"
    result = ""
    while value:
        value, remainder = divmod(value, 36)
        result = alphabet[remainder] + result
    return result


def decode_queue_event(raw: str) -> dict[str, Any]:
    try:
        event = json.loads(raw)
        return event if isinstance(event, dict) else {"event_type": "raw", "payload": {"raw": raw}}
    except json.JSONDecodeError:
        return {"event_type": "raw", "payload": {"raw": raw}}


def worker_source_status(state: Any) -> str:
    if state in {"idle", "processing"}:
        return "ok"
    if state == "unknown":
        return "missing"
    if state == "unavailable":
        return "unavailable"
    return "invalid"


def read_worker_status(redis_client: redis.Redis, worker_status_key: str) -> tuple[dict[str, Any], str | None]:
    try:
        raw = redis_client.get(worker_status_key)
    except redis.RedisError:
        return {"state": "unavailable"}, "Worker status is unavailable"
    if raw is None:
        return {"state": "unknown"}, None
    try:
        status = json.loads(raw)
    except json.JSONDecodeError:
        return {"state": "invalid"}, "Worker status is invalid"
    if not isinstance(status, dict):
        return {"state": "invalid"}, "Worker status must be a JSON object"
    if status.get("state") not in {"idle", "processing"}:
        return {"state": "invalid"}, "Worker status has an unknown state"
    if status["state"] == "processing" and not isinstance(status.get("event"), dict):
        return {"state": "invalid"}, "Worker processing status has no event object"
    return status, None


def worker_stage(
    redis_client: redis.Redis, worker_status_key: str
) -> tuple[dict[str, Any], str, str | None, dict[str, Any] | None, str]:
    status, warning = read_worker_status(redis_client, worker_status_key)
    running_item: dict[str, Any] | None = None
    running_fingerprint = ""
    if status.get("state") == "processing":
        event = status.get("event")
        if isinstance(event, dict):
            running_fingerprint = event_fingerprint(event)
            running_item = {
                "id": f"running-{running_fingerprint}",
                "status": "running",
                "source": "worker",
                "started_at": status.get("started_at", ""),
                "event": event,
            }
    return status, worker_source_status(status.get("state")), warning, running_item, running_fingerprint


def pending_stage(
    redis_client: redis.Redis, limit: int, queue_name: str
) -> tuple[list[dict[str, Any]], int, str, str | None]:
    try:
        queue_length = redis_client.llen(queue_name)
        start = max(queue_length - limit, 0)
        raw_items = redis_client.lrange(queue_name, start, queue_length - 1)
    except redis.RedisError:
        return [], 0, "unavailable", "Redis queue is unavailable"

    counts: dict[str, int] = {}
    items: list[dict[str, Any]] = []
    for index in range(len(raw_items) - 1, -1, -1):
        event = decode_queue_event(raw_items[index])
        fingerprint = event_fingerprint(event)
        counts[fingerprint] = counts.get(fingerprint, 0) + 1
        items.append(
            {
                "id": f"pending-{fingerprint}-{counts[fingerprint]}",
                "status": "pending",
                "source": "redis",
                "position": len(raw_items) - index,
                "fingerprint": fingerprint,
                "event": event,
            }
        )
    return items, queue_length, "ok", None


def history_stage(
    limit: int, running_fingerprint: str, history_collection: Collection
) -> tuple[list[dict[str, Any]], str, str | None]:
    try:
        documents = list(history_collection.find({}).sort("_id", DESCENDING).limit(limit))
    except PyMongoError:
        return [], "unavailable", "MongoDB history is unavailable"

    running_index = -1
    if running_fingerprint:
        for index, document in enumerate(documents):
            event = {key: value for key, value in document.items() if key not in {"_id", "created_at"}}
            if event_fingerprint(event) == running_fingerprint:
                running_index = index
                break

    items: list[dict[str, Any]] = []
    for index, document in enumerate(documents):
        if index == running_index:
            continue
        created_at = document.get("created_at")
        event = {key: value for key, value in document.items() if key not in {"_id", "created_at"}}
        fingerprint = event_fingerprint(event)
        items.append(
            {
                "id": f"done-{fingerprint}-{created_at}",
                "status": "done",
                "source": "mongodb",
                "created_at": created_at,
                "doc_id": str(document.get("_id", "")),
                "event": event,
            }
        )
    return items, "ok", None


def event_snapshot(
    redis_client: redis.Redis,
    limit: int,
    queue_name: str,
    history_collection: Collection,
    worker_status_key: str,
) -> dict[str, Any]:
    worker, worker_source, worker_warning, running_item, running_fingerprint = worker_stage(
        redis_client, worker_status_key
    )
    pending_items, pending_count, redis_source, redis_warning = pending_stage(redis_client, limit, queue_name)
    history_items, mongo_source, mongo_warning = history_stage(limit, running_fingerprint, history_collection)

    snapshot: dict[str, Any] = {
        "queue": queue_name,
        "fetched_at": datetime.now(timezone.utc),
        "worker": worker,
        "summary": {
            "pending": pending_count,
            "running": 1 if running_item else 0,
            "history": len(history_items),
        },
        "sources": {"mongodb": mongo_source, "redis": redis_source, "worker": worker_source},
        "items": list(reversed(history_items)),
    }

    warnings = {}
    if worker_warning:
        warnings["worker"] = worker_warning
    if redis_warning:
        warnings["redis"] = redis_warning
    if mongo_warning:
        warnings["mongodb"] = mongo_warning
    if warnings:
        snapshot["warnings"] = warnings

    if running_item:
        snapshot["items"].append(running_item)
    snapshot["items"].extend(pending_items)
    return snapshot


DELETE_PENDING_SCRIPT = """
local current = redis.call('LINDEX', KEYS[1], -tonumber(ARGV[1]))
if not current then return 0 end
if current ~= ARGV[2] then return -1 end
redis.call('LSET', KEYS[1], -tonumber(ARGV[1]), ARGV[3])
return redis.call('LREM', KEYS[1], 1, ARGV[3])
"""

UPDATE_PENDING_SCRIPT = """
local current = redis.call('LINDEX', KEYS[1], -tonumber(ARGV[1]))
if not current then return 0 end
if current ~= ARGV[2] then return -1 end
redis.call('LSET', KEYS[1], -tonumber(ARGV[1]), ARGV[3])
return 1
"""


def create_events_router(
    redis_client: redis.Redis,
    history: Collection,
    queue_name: str,
    worker_status_key: str,
) -> APIRouter:
    router = APIRouter()

    @router.get("/api/events")
    def events(limit: int = Query(150)):
        error = limit_error(limit)
        if error:
            return error
        return event_snapshot(redis_client, limit, queue_name, history, worker_status_key)

    @router.delete("/api/events")
    def delete_event(payload: DeleteEventRequest):
        if payload.status == "done":
            if not payload.doc_id:
                return JSONResponse(status_code=400, content={"error": "缺少历史记录 ID"})
            try:
                object_id = ObjectId(payload.doc_id)
            except InvalidId:
                return JSONResponse(status_code=400, content={"error": "历史记录 ID 无效"})
            try:
                result = history.delete_one({"_id": object_id})
            except PyMongoError:
                return JSONResponse(status_code=503, content={"error": "MongoDB 历史暂时不可用"})
            if result.deleted_count == 0:
                return JSONResponse(status_code=404, content={"error": "历史记录不存在或已被删除"})
            return {"deleted": True, "status": "done"}

        if payload.status == "pending":
            if payload.position is None or payload.position < 1 or not payload.fingerprint:
                return JSONResponse(status_code=400, content={"error": "缺少队列位置或事件指纹"})
            try:
                raw = redis_client.lindex(queue_name, -payload.position)
            except redis.RedisError:
                return JSONResponse(status_code=503, content={"error": "Redis 队列暂时不可用"})
            if raw is None:
                return JSONResponse(status_code=404, content={"error": "队列事件不存在或已被处理"})
            if event_fingerprint(decode_queue_event(raw)) != payload.fingerprint:
                return JSONResponse(status_code=409, content={"error": "队列已发生变化，请刷新后重试"})
            marker = f"__aagent_deleted__{uuid.uuid4().hex}"
            try:
                removed = redis_client.eval(DELETE_PENDING_SCRIPT, 1, queue_name, str(payload.position), raw, marker)
            except redis.RedisError:
                return JSONResponse(status_code=503, content={"error": "Redis 队列暂时不可用"})
            if removed == -1:
                return JSONResponse(status_code=409, content={"error": "队列已发生变化，请刷新后重试"})
            if removed == 0:
                return JSONResponse(status_code=404, content={"error": "队列事件不存在或已被处理"})
            return {"deleted": True, "status": "pending"}

        return JSONResponse(status_code=400, content={"error": "不支持删除该状态的事件"})

    @router.put("/api/events")
    def update_event(payload: UpdateEventRequest):
        event = {key: value for key, value in payload.event.items() if key not in {"_id", "created_at"}}
        if not event:
            return JSONResponse(status_code=400, content={"error": "事件内容不能为空"})
        if not isinstance(event.get("event_type"), str) or not event["event_type"].strip():
            return JSONResponse(status_code=400, content={"error": "事件缺少有效的 event_type 字段"})
        encoded = json.dumps(event, ensure_ascii=False)
        if len(encoded.encode("utf-8")) > MAX_EVENT_BODY_BYTES:
            return JSONResponse(status_code=400, content={"error": "事件内容不能超过 256 KB"})

        if payload.status == "done":
            if not payload.doc_id:
                return JSONResponse(status_code=400, content={"error": "缺少历史记录 ID"})
            try:
                object_id = ObjectId(payload.doc_id)
            except InvalidId:
                return JSONResponse(status_code=400, content={"error": "历史记录 ID 无效"})
            try:
                existing = history.find_one({"_id": object_id}, {"created_at": 1})
                if existing is None:
                    return JSONResponse(status_code=404, content={"error": "历史记录不存在或已被删除"})
                document = dict(event)
                if "created_at" in existing:
                    document["created_at"] = existing["created_at"]
                history.replace_one({"_id": object_id}, document)
            except PyMongoError:
                return JSONResponse(status_code=503, content={"error": "MongoDB 历史暂时不可用"})
            return {"updated": True, "status": "done", "doc_id": payload.doc_id, "fingerprint": event_fingerprint(event)}

        if payload.status == "pending":
            if payload.position is None or payload.position < 1 or not payload.fingerprint:
                return JSONResponse(status_code=400, content={"error": "缺少队列位置或事件指纹"})
            try:
                raw = redis_client.lindex(queue_name, -payload.position)
            except redis.RedisError:
                return JSONResponse(status_code=503, content={"error": "Redis 队列暂时不可用"})
            if raw is None:
                return JSONResponse(status_code=404, content={"error": "队列事件不存在或已被处理"})
            if event_fingerprint(decode_queue_event(raw)) != payload.fingerprint:
                return JSONResponse(status_code=409, content={"error": "队列已发生变化，请刷新后重试"})
            try:
                updated = redis_client.eval(UPDATE_PENDING_SCRIPT, 1, queue_name, str(payload.position), raw, encoded)
            except redis.RedisError:
                return JSONResponse(status_code=503, content={"error": "Redis 队列暂时不可用"})
            if updated == -1:
                return JSONResponse(status_code=409, content={"error": "队列已发生变化，请刷新后重试"})
            if updated == 0:
                return JSONResponse(status_code=404, content={"error": "队列事件不存在或已被处理"})
            return {"updated": True, "status": "pending", "position": payload.position, "fingerprint": event_fingerprint(event)}

        return JSONResponse(status_code=400, content={"error": "不支持修改该状态的事件"})

    @router.get("/api/terminal/history")
    def terminal_history(limit: int = Query(150)):
        error = limit_error(limit)
        if error:
            return error
        try:
            documents = list(
                history.find({"event_type": {"$in": ["terminal", "response"]}})
                .sort("_id", DESCENDING)
                .limit(limit)
            )
        except PyMongoError:
            return JSONResponse(status_code=503, content={"error": "终端历史暂时不可用"})

        items = []
        for document in reversed(documents):
            object_id = document.get("_id")
            created_at = document.get("created_at")
            event = {key: value for key, value in document.items() if key not in {"_id", "created_at"}}
            items.append({"id": str(object_id) if object_id else "", "created_at": created_at, "event": event})
        return {"fetched_at": datetime.now(timezone.utc), "items": items}

    @router.post("/api/terminal", status_code=201)
    def submit_terminal(payload: TerminalRequest):
        message = payload.message.strip()
        if not message:
            return JSONResponse(status_code=400, content={"error": "消息不能为空"})
        if len(message) > MAX_TERMINAL_RUNES:
            return JSONResponse(status_code=400, content={"error": "消息不能超过 4000 个字符"})
        if payload.files:
            return JSONResponse(status_code=400, content={"error": "暂不支持文件附件"})

        event = {
            "event_type": "terminal",
            "time": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "payload": {"message": message, "files": []},
        }
        try:
            redis_client.rpush(queue_name, json.dumps(event, ensure_ascii=False, separators=(",", ":")))
        except redis.RedisError:
            return JSONResponse(status_code=503, content={"error": "消息队列暂时不可用"})
        return {"event": event, "queue": queue_name}

    return router