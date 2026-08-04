import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import redis
from bson import ObjectId
from bson.errors import InvalidId
from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from pymongo import MongoClient, DESCENDING
from pymongo.collection import Collection
from pymongo.errors import PyMongoError

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("aagent.webui")

MAX_TERMINAL_RUNES = 4000
MAX_TERMINAL_BODY_BYTES = 16 * 1024
MAX_SYSTEM_PROMPT_CHARS = 100_000
MAX_SETTINGS_BODY_BYTES = 512 * 1024


def env(name: str, fallback: str) -> str:
    return os.getenv(name) or fallback


def redis_address() -> str:
    explicit = os.getenv("REDIS_ADDR")
    if explicit:
        return explicit
    return f"{env('REDIS_HOST', 'redis')}:{env('REDIS_PORT', '6379')}"


REDIS_ADDRESS = redis_address()
REDIS_DB = int(env("REDIS_DB", "0"))
QUEUE_NAME = env("AGENT_QUEUE_NAME", "agent_tasks")
WORKER_STATUS_KEY = env("AGENT_WORKER_STATUS_KEY", "aagent:worker:status")
SYSTEM_PROMPT_KEY = env("AGENT_SYSTEM_PROMPT_KEY", "aagent:settings:system_prompt")
MONGO_HOST = env("MONGO_HOST", "mongodb")
MONGO_PORT = int(env("MONGO_PORT", "27017"))
MONGO_DATABASE = env("MONGO_DATABASE", "agent")
MONGO_HISTORY_COLLECTION = env("MONGO_HISTORY_COLLECTION", "event_history")

redis_client = redis.Redis.from_url(
    f"redis://{REDIS_ADDRESS}/{REDIS_DB}",
    password=os.getenv("REDIS_PASSWORD") or None,
    decode_responses=True,
    socket_connect_timeout=5,
    socket_timeout=5,
)
mongo_kwargs: dict[str, Any] = {
    "host": MONGO_HOST,
    "port": MONGO_PORT,
    "serverSelectionTimeoutMS": 5000,
    "tz_aware": True,
}
if os.getenv("MONGO_USER"):
    mongo_kwargs.update(
        username=os.environ["MONGO_USER"],
        password=os.getenv("MONGO_PASS", ""),
        authSource="admin",
    )
mongo_client = MongoClient(**mongo_kwargs)
history: Collection = mongo_client[MONGO_DATABASE][MONGO_HISTORY_COLLECTION]


class TerminalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str
    files: list[str] = Field(default_factory=list)


class SystemPromptRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    system_prompt: str


class DeleteEventRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str
    doc_id: str | None = None
    position: int | None = None
    fingerprint: str | None = None


app = FastAPI(title="AAgent WebUI")


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["Content-Security-Policy"] = "default-src 'self'; style-src 'self'; script-src 'self'; connect-src 'self'; img-src 'self' data:"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


@app.middleware("http")
async def request_logger(request: Request, call_next):
    started = time.perf_counter()
    response = await call_next(request)
    if request.url.path.startswith("/api/"):
        logger.info("request method=%s path=%s duration=%.3fs", request.method, request.url.path, time.perf_counter() - started)
    return response


@app.middleware("http")
async def terminal_body_guard(request: Request, call_next):
    body_limits = {
        "/api/terminal": (MAX_TERMINAL_BODY_BYTES, "请求体不能超过 16 KB"),
        "/api/settings/system-prompt": (MAX_SETTINGS_BODY_BYTES, "请求体不能超过 512 KB"),
    }
    if request.method == "POST" and request.url.path in body_limits:
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                limit, error_message = body_limits[request.url.path]
                if int(content_length) > limit:
                    return JSONResponse(status_code=400, content={"error": error_message})
            except ValueError:
                pass
    return await call_next(request)


def limit_error(limit: int) -> JSONResponse | None:
    if limit < 1 or limit > 300:
        return JSONResponse(status_code=400, content={"error": "limit must be between 1 and 300"})
    return None


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


def read_worker_status() -> tuple[dict[str, Any], str | None]:
    try:
        raw = redis_client.get(WORKER_STATUS_KEY)
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


def worker_stage() -> tuple[dict[str, Any], str, str | None, dict[str, Any] | None, str]:
    status, warning = read_worker_status()
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


def pending_stage(limit: int) -> tuple[list[dict[str, Any]], int, str, str | None]:
    try:
        queue_length = redis_client.llen(QUEUE_NAME)
        start = max(queue_length - limit, 0)
        raw_items = redis_client.lrange(QUEUE_NAME, start, queue_length - 1)
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


def history_stage(limit: int, running_fingerprint: str) -> tuple[list[dict[str, Any]], str, str | None]:
    try:
        documents = list(history.find({}).sort("_id", DESCENDING).limit(limit))
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


def event_snapshot(limit: int) -> dict[str, Any]:
    worker, worker_source, worker_warning, running_item, running_fingerprint = worker_stage()
    pending_items, pending_count, redis_source, redis_warning = pending_stage(limit)
    history_items, mongo_source, mongo_warning = history_stage(limit, running_fingerprint)

    snapshot: dict[str, Any] = {
        "queue": QUEUE_NAME,
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


@app.get("/api/health")
def health():
    try:
        redis_client.ping()
    except redis.RedisError as error:
        return JSONResponse(status_code=503, content={"status": "unavailable", "error": str(error)})
    return {"status": "ok"}


@app.get("/api/events")
def events(limit: int = Query(150)):
    error = limit_error(limit)
    if error:
        return error
    return event_snapshot(limit)


DELETE_PENDING_SCRIPT = """
local current = redis.call('LINDEX', KEYS[1], -tonumber(ARGV[1]))
if not current then return 0 end
if current ~= ARGV[2] then return -1 end
redis.call('LSET', KEYS[1], -tonumber(ARGV[1]), ARGV[3])
return redis.call('LREM', KEYS[1], 1, ARGV[3])
"""


@app.delete("/api/events")
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
            raw = redis_client.lindex(QUEUE_NAME, -payload.position)
        except redis.RedisError:
            return JSONResponse(status_code=503, content={"error": "Redis 队列暂时不可用"})
        if raw is None:
            return JSONResponse(status_code=404, content={"error": "队列事件不存在或已被处理"})
        if event_fingerprint(decode_queue_event(raw)) != payload.fingerprint:
            return JSONResponse(status_code=409, content={"error": "队列已发生变化，请刷新后重试"})
        marker = f"__aagent_deleted__{uuid.uuid4().hex}"
        try:
            removed = redis_client.eval(DELETE_PENDING_SCRIPT, 1, QUEUE_NAME, str(payload.position), raw, marker)
        except redis.RedisError:
            return JSONResponse(status_code=503, content={"error": "Redis 队列暂时不可用"})
        if removed == -1:
            return JSONResponse(status_code=409, content={"error": "队列已发生变化，请刷新后重试"})
        if removed == 0:
            return JSONResponse(status_code=404, content={"error": "队列事件不存在或已被处理"})
        return {"deleted": True, "status": "pending"}

    return JSONResponse(status_code=400, content={"error": "不支持删除该状态的事件"})


@app.get("/api/settings")
def settings():
    try:
        system_prompt = redis_client.get(SYSTEM_PROMPT_KEY)
    except redis.RedisError:
        return JSONResponse(status_code=503, content={"error": "设置暂时不可用"})
    if system_prompt is None:
        return JSONResponse(status_code=503, content={"error": "Agent 尚未初始化设置"})
    return {"system_prompt": system_prompt}


@app.post("/api/settings/system-prompt", status_code=202)
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
        redis_client.rpush(QUEUE_NAME, json.dumps(event, ensure_ascii=False, separators=(",", ":")))
    except redis.RedisError:
        return JSONResponse(status_code=503, content={"error": "消息队列暂时不可用"})
    return {"event": event, "queue": QUEUE_NAME}


@app.get("/api/terminal/history")
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


@app.post("/api/terminal", status_code=201)
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
        redis_client.rpush(QUEUE_NAME, json.dumps(event, ensure_ascii=False, separators=(",", ":")))
    except redis.RedisError:
        return JSONResponse(status_code=503, content={"error": "消息队列暂时不可用"})
    return {"event": event, "queue": QUEUE_NAME}


static_directory = Path(__file__).parent / "static"
app.mount("/", StaticFiles(directory=static_directory, html=True), name="static")

logger.info("event console configured address=%s queue=%s", REDIS_ADDRESS, QUEUE_NAME)
