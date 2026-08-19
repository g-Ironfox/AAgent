import json
from datetime import datetime, timezone

import redis
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

MAX_SYSTEM_PROMPT_CHARS = 100_000


class SystemPromptRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    system_prompt: str


class MaxContextCountRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_context_count: str


def create_settings_router(redis_client: redis.Redis, settings_key: str, queue_name: str) -> APIRouter:
    router = APIRouter(prefix="/api/settings")

    @router.get("")
    def settings():
        try:
            raw = redis_client.get(settings_key)
        except redis.RedisError:
            return JSONResponse(status_code=503, content={"error": "设置暂时不可用"})
        if raw is None:
            return JSONResponse(status_code=503, content={"error": "Agent 尚未初始化设置"})
        try:
            data = json.loads(raw)
        except (TypeError, ValueError):
            data = None
        if not isinstance(data, dict) or not isinstance(data.get("system_prompt"), str):
            return JSONResponse(status_code=503, content={"error": "Agent 尚未初始化设置"})
        return data

    @router.post("/system-prompt", status_code=202)
    def update_system_prompt(payload: SystemPromptRequest):
        system_prompt = payload.system_prompt
        if not system_prompt.strip():
            return JSONResponse(status_code=400, content={"error": "System prompt 不能为空"})
        if len(system_prompt) > MAX_SYSTEM_PROMPT_CHARS:
            return JSONResponse(status_code=400, content={"error": "System prompt 不能超过 100000 个字符"})

        event = {
            "event_type": "setting",
            "time": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "payload": {"system_prompt": system_prompt},
        }
        try:
            redis_client.rpush(queue_name, json.dumps(event, ensure_ascii=False, separators=(",", ":")))
        except redis.RedisError:
            return JSONResponse(status_code=503, content={"error": "消息队列暂时不可用"})
        return {"event": event, "queue": queue_name}

    @router.post("/max-context-count", status_code=202)
    def update_max_context_count(payload: MaxContextCountRequest):
        max_context_count = payload.max_context_count.strip()
        if not max_context_count.isdigit() or int(max_context_count) <= 0:
            return JSONResponse(status_code=400, content={"error": "最大召回窗口必须是正整数"})

        event = {
            "event_type": "setting",
            "time": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "payload": {"max_context_count": max_context_count},
        }
        try:
            redis_client.rpush(queue_name, json.dumps(event, ensure_ascii=False, separators=(",", ":")))
        except redis.RedisError:
            return JSONResponse(status_code=503, content={"error": "消息队列暂时不可用"})
        return {"event": event, "queue": queue_name}

    return router