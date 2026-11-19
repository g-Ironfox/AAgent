"""Terminal messages are stored in MongoDB and signalled to the Agent runtime."""

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
TERMINAL_SESSIONS = os.getenv("TerminalSessions", "terminal_sessions")
EXTERNAL_EVENTS = os.getenv("ExternalEvents", "external_events")
logger = logging.getLogger(__name__)


class TerminalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str
    files: list[str] = Field(default_factory=list)
    terminal_id: str = Field(min_length=1, max_length=256)


def serialize_message(document: dict) -> dict:
    message = {
        "id": str(document["_id"]),
        "role": document["role"],
        "content": document["content"],
        "created_at": document["created_at"],
    }
    if document.get("terminal_id"):
        message["terminal_id"] = document["terminal_id"]
    return message


def create_terminal_router(redis_client: redis.Redis, messages: Collection) -> APIRouter:
    router = APIRouter()

    @router.get("/api/terminal/sessions")
    def terminal_sessions():
        try:
            records = redis_client.hgetall(TERMINAL_SESSIONS)
        except redis.RedisError:
            return JSONResponse(status_code=503, content={"error": "terminal sessions unavailable"})
        sessions = []
        for terminal_id, raw in records.items():
            try:
                record = json.loads(raw)
            except (TypeError, ValueError):
                continue
            if (
                not isinstance(record, dict)
                or record.get("terminal_id") != terminal_id
                or record.get("status") not in {"open", "closed"}
            ):
                continue
            sessions.append({
                "terminal_id": terminal_id,
                "status": record["status"],
                "start_time": record.get("start_time"),
                "closed_at": record.get("closed_at"),
                "workflow_name": record.get("workflow_name"),
                "workflow_status": record.get("workflow_status"),
                "wait_kind": record.get("wait_kind"),
            })
        sessions.sort(key=lambda item: item.get("start_time") or "", reverse=True)
        return {"sessions": sessions}

    @router.get("/api/terminal/history")
    def terminal_history(
        limit: int = Query(150), terminal_id: str = Query(..., min_length=1)
    ):
        error = limit_error(limit)
        if error:
            return error
        try:
            documents = list(
                messages.find({"terminal_id": terminal_id})
                .sort([("created_at", DESCENDING), ("_id", DESCENDING)])
                .limit(limit)
            )
        except PyMongoError:
            return JSONResponse(status_code=503, content={"error": "terminal history unavailable"})
        return {
            "fetched_at": datetime.now(timezone.utc),
            "items": [serialize_message(document) for document in reversed(documents)],
        }

    @router.post("/api/terminal", status_code=201)
    def submit_terminal(payload: TerminalRequest):
        content = payload.content.strip()
        if not content:
            return JSONResponse(status_code=400, content={"error": "message cannot be empty"})
        if len(content) > MAX_TERMINAL_RUNES:
            return JSONResponse(status_code=400, content={"error": "message exceeds 4000 characters"})
        if payload.files:
            return JSONResponse(status_code=400, content={"error": "file attachments are not supported"})

        now = datetime.now(timezone.utc)
        document = {
            "_id": ObjectId(),
            "role": "user",
            "content": content,
            "created_at": now,
            "terminal_id": payload.terminal_id,
        }
        try:
            messages.insert_one(document)
        except PyMongoError:
            return JSONResponse(status_code=503, content={"error": "failed to save terminal message"})
        try:
            redis_client.lpush(EXTERNAL_EVENTS, json.dumps({
                "type": "terminal_message",
                "terminal_id": payload.terminal_id,
            }, ensure_ascii=False))
        except redis.RedisError:
            logger.exception("terminal message saved but event queueing failed")
            return JSONResponse(status_code=503, content={
                "error": "terminal message saved but event queueing failed",
                "message": serialize_message(document) | {"created_at": now.isoformat()},
            })
        return {"message": serialize_message(document)}

    return router
