"""Terminal messages are stored separately from workflow events."""

import json
import logging
import os
from datetime import datetime, timezone

import redis
from bson import ObjectId
from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from pymongo import DESCENDING
from pymongo.collection import Collection
from pymongo.errors import PyMongoError

from common import limit_error

MAX_TERMINAL_RUNES = 4000
PROCESS_TABLE_KEY = os.getenv("ProcessTable", "processtable")
logger = logging.getLogger(__name__)


class TerminalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str
    files: list[str] = Field(default_factory=list)
    terminal_process_id: str | None = Field(default=None, min_length=1, max_length=256)


def serialize_message(document: dict) -> dict:
    message = {
        "id": str(document["_id"]),
        "role": document["role"],
        "content": document["content"],
        "created_at": document["created_at"],
    }
    if document.get("terminal_process_id"):
        message["terminal_process_id"] = document["terminal_process_id"]
    return message


def create_terminal_router(redis_client: redis.Redis, messages: Collection, queue_name: str) -> APIRouter:
    router = APIRouter()

    @router.get("/api/terminal/sessions")
    def terminal_sessions():
        try:
            records = redis_client.hgetall(PROCESS_TABLE_KEY)
        except redis.RedisError:
            return JSONResponse(status_code=503, content={"error": "终端列表暂时不可用"})
        sessions = []
        for process_id, raw in records.items():
            try:
                process = json.loads(raw)
            except (TypeError, ValueError):
                continue
            if (
                not isinstance(process, dict)
                or process.get("process_type") != "terminal"
                or not isinstance(process.get("process_id"), str)
                or process["process_id"] != process_id
            ):
                continue
            sessions.append({
                "terminal_process_id": process.get("process_id"),
                "parent_process_id": process.get("parent_process_id"),
                "status": process.get("status", "unknown"),
                "start_time": process.get("start_time"),
            })
        sessions.sort(key=lambda item: item.get("start_time") or "", reverse=True)
        return {"sessions": sessions}

    @router.get("/api/terminal/history")
    def terminal_history(
        limit: int = Query(150), terminal_process_id: str | None = None
    ):
        error = limit_error(limit)
        if error:
            return error
        query = (
            {"terminal_process_id": terminal_process_id}
            if terminal_process_id
            else {"terminal_process_id": {"$exists": False}}
        )
        try:
            documents = list(
                messages.find(query)
                .sort([("created_at", DESCENDING), ("_id", DESCENDING)])
                .limit(limit)
            )
        except PyMongoError:
            return JSONResponse(status_code=503, content={"error": "终端历史暂时不可用"})
        return {
            "fetched_at": datetime.now(timezone.utc),
            "items": [serialize_message(document) for document in reversed(documents)],
        }

    @router.post("/api/terminal", status_code=201)
    def submit_terminal(payload: TerminalRequest):
        content = payload.content.strip()
        if not content:
            return JSONResponse(status_code=400, content={"error": "消息不能为空"})
        if len(content) > MAX_TERMINAL_RUNES:
            return JSONResponse(status_code=400, content={"error": "消息不能超过 4000 个字符"})
        if payload.files:
            return JSONResponse(status_code=400, content={"error": "暂不支持文件附件"})

        if payload.terminal_process_id:
            try:
                raw_process = redis_client.hget(PROCESS_TABLE_KEY, payload.terminal_process_id)
            except redis.RedisError:
                return JSONResponse(status_code=503, content={"error": "终端进程暂时不可用"})
            if raw_process is None:
                return JSONResponse(status_code=404, content={"error": "终端不存在"})
            try:
                terminal_process = json.loads(raw_process)
            except (TypeError, ValueError):
                return JSONResponse(status_code=503, content={"error": "终端进程数据无效"})
            if (
                not isinstance(terminal_process, dict)
                or terminal_process.get("process_type") != "terminal"
                or terminal_process.get("process_id") != payload.terminal_process_id
            ):
                return JSONResponse(status_code=404, content={"error": "终端不存在"})
            if terminal_process.get("status") == "terminated":
                return JSONResponse(status_code=409, content={"error": "该终端已关闭"})

        now = datetime.now(timezone.utc)
        document = {
            "_id": ObjectId(),
            "role": "user",
            "content": content,
            "created_at": now,
        }
        event = {
            "version": "1.1",
            "event_type": "terminal",
            "time": now.isoformat().replace("+00:00", "Z"),
            "payload": {"content": content, "files": []},
        }
        if payload.terminal_process_id:
            document["terminal_process_id"] = payload.terminal_process_id
            event["payload"]["terminal_process_id"] = payload.terminal_process_id
        try:
            messages.insert_one(document)
        except PyMongoError:
            return JSONResponse(status_code=503, content={"error": "终端消息保存失败"})
        try:
            redis_client.rpush(queue_name, json.dumps(event, ensure_ascii=False, separators=(",", ":")))
        except redis.RedisError:
            try:
                messages.delete_one({"_id": document["_id"]})
            except PyMongoError:
                logger.exception("Failed to remove terminal message after queue failure")
            return JSONResponse(status_code=503, content={"error": "消息队列暂时不可用"})
        return {"event": event, "queue": queue_name, "message": serialize_message(document)}

    return router
