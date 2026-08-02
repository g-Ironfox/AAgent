import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import redis
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
    if request.method == "POST" and request.url.path == "/api/terminal":
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > MAX_TERMINAL_BODY_BYTES:
                    return JSONResponse(status_code=400, content={"error": "请求体不能超过 16 KB"})
            except ValueError:
                pass
    return await call_next(request)


def validate_limit(limit: int) -> int | JSONResponse:
    if limit < 1 or limit > 300:
        return JSONResponse(status_code=400, content={"error": "limit must be between 1 and 300"})
    return limit


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


def worker_source_status(state: str) -> str:
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
    if status.get("state") not in {"idle", "processing"}:
        return {"state": "invalid"}, "Worker status has an unknown state"
    if status["state"] == "processing" and "event" not in status:
        return {"state": "invalid"}, "Worker processing status has no event"
    return status, None


def event_snapshot(limit: int) -> dict[str, Any]:
    snapshot: dict[str, Any] = {
        "queue": QUEUE_NAME,
        "fetched_at": datetime.now(timezone.utc),
        "worker": {"state": "unknown"},
        "summary": {"pending": 0, "running": 0, "history": 0},
        "sources": {"mongodb": "unavailable", "redis": "unavailable", "worker": "unavailable"},
        "items": [],
        "warnings": {},
    }
    pending_items: list[dict[str, Any]] = []

    status, status_error = read_worker_status()
    snapshot["worker"] = status
    snapshot["sources"]["worker"] = worker_source_status(status.get("state", "invalid"))
    if status_error:
        snapshot["warnings"]["worker"] = status_error

    running_fingerprint = ""
    running = None
    if status.get("state") == "processing":
        snapshot["summary"]["running"] = 1
        event = status.get("event")
        if isinstance(event, dict):
            running_fingerprint = event_fingerprint(event)
            running = {
                "id": f"running-{running_fingerprint}",
                "status": "running",
                "source": "worker",
                "started_at": status.get("started_at", ""),
                "event": event,
            }

    try:
        queue_length = redis_client.llen(QUEUE_NAME)
        snapshot["sources"]["redis"] = "ok"
        snapshot["summary"]["pending"] = queue_length
        start = max(queue_length - limit, 0)
        raw_items = redis_client.lrange(QUEUE_NAME, start, queue_length - 1)
        seen: dict[str, int] = {}
        for index in range(len(raw_items) - 1, -1, -1):
            event = decode_queue_event(raw_items[index])
            fingerprint = event_fingerprint(event)
            seen[fingerprint] = seen.get(fingerprint, 0) + 1
            pending_items.append(
                {
                    "id": f"pending-{fingerprint}-{seen[fingerprint]}",
                    "status": "pending",
                    "source": "redis",
                    "position": len(raw_items) - index,
                    "event": event,
                }
            )
    except redis.RedisError:
        snapshot["warnings"]["redis"] = "Redis queue is unavailable"

    try:
        documents = list(history.find({}, {"_id": 0}).sort("_id", DESCENDING).limit(limit))
        snapshot["sources"]["mongodb"] = "ok"
        running_index = -1
        if running_fingerprint:
            for index, document in enumerate(documents):
                event = {key: value for key, value in document.items() if key != "created_at"}
                if event_fingerprint(event) == running_fingerprint:
                    running_index = index
                    break
        history_items = []
        for index, document in enumerate(documents):
            created_at = document.pop("created_at", None)
            event = document
            fingerprint = event_fingerprint(event)
            if index == running_index:
                continue
            history_items.append(
                {
                    "id": f"done-{fingerprint}-{created_at}",
                    "status": "done",
                    "source": "mongodb",
                    "created_at": created_at,
                    "event": event,
                }
            )
            snapshot["summary"]["history"] += 1
        snapshot["items"].extend(reversed(history_items))
    except PyMongoError:
        snapshot["warnings"]["mongodb"] = "MongoDB history is unavailable"

    if running:
        snapshot["items"].append(running)
    snapshot["items"].extend(pending_items)
    if not snapshot["warnings"]:
        snapshot.pop("warnings")
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
    checked = validate_limit(limit)
    if isinstance(checked, JSONResponse):
        return checked
    return event_snapshot(checked)


@app.get("/api/terminal/history")
def terminal_history(limit: int = Query(150)):
    checked = validate_limit(limit)
    if isinstance(checked, JSONResponse):
        return checked
    limit = checked
    try:
        documents = list(
            history.find({"event_type": {"$in": ["webui", "response"]}})
            .sort("_id", DESCENDING)
            .limit(limit)
        )
    except PyMongoError:
        return JSONResponse(status_code=503, content={"error": "终端历史暂时不可用"})

    items = []
    for document in reversed(documents):
        object_id = document.pop("_id", None)
        created_at = document.pop("created_at", None)
        items.append({"id": str(object_id) if object_id else "", "created_at": created_at, "event": document})
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
        "event_type": "webui",
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
