"""Terminal messages are stored separately from workflow events."""

import json
import logging
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
logger = logging.getLogger(__name__)


class TerminalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str
    files: list[str] = Field(default_factory=list)


def serialize_message(document: dict) -> dict:
    return {
        "id": str(document["_id"]),
        "role": document["role"],
        "content": document["content"],
        "created_at": document["created_at"],
    }


def create_terminal_router(redis_client: redis.Redis, messages: Collection, queue_name: str) -> APIRouter:
    router = APIRouter()

    @router.get("/api/terminal/history")
    def terminal_history(limit: int = Query(150)):
        error = limit_error(limit)
        if error:
            return error
        try:
            documents = list(
                messages.find({})
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

        now = datetime.now(timezone.utc)
        document = {"_id": ObjectId(), "role": "user", "content": content, "created_at": now}
        event = {
            "version": "1.1",
            "event_type": "terminal",
            "time": now.isoformat().replace("+00:00", "Z"),
            "payload": {"content": content, "files": []},
        }
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
