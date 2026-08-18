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
from pymongo.errors import DuplicateKeyError, PyMongoError

from documents import create_documents_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("aagent.webui")

MAX_TERMINAL_RUNES = 4000
MAX_TERMINAL_BODY_BYTES = 16 * 1024
MAX_SYSTEM_PROMPT_CHARS = 100_000
MAX_SETTINGS_BODY_BYTES = 512 * 1024
MAX_EVENT_BODY_BYTES = 256 * 1024
MAX_DOCUMENT_BODY_BYTES = 1024 * 1024
MAX_SUBAGENT_DOCUMENTS = 100
MAX_WORKFLOW_BODY_BYTES = 512 * 1024
MAX_WORKFLOW_NODES = 200
MAX_WORKFLOW_CONNECTIONS = 1000


def env(name: str, fallback: str) -> str:
    return os.getenv(name) or fallback


def redis_address() -> str:
    explicit = os.getenv("REDIS_ADDR")
    if explicit:
        return explicit
    return f"{env('REDIS_HOST', 'redis')}:{env('REDIS_PORT', '6379')}"


REDIS_ADDRESS = redis_address()
REDIS_DB = int(env("REDIS_DB", "0"))
QUEUE_NAME = env("MAIN_AGENT_QUEUE_NAME", "main_agent_queue")
WORKER_STATUS_KEY = env("AGENT_WORKER_STATUS_KEY", "aagent:worker:status")
SETTINGS_KEY = env("AGENT_SETTINGS_KEY", "aagent:settings")
TOOLS_KEY = env("AGENT_TOOLS_KEY", "aagent:tools")
MONGO_HOST = env("MONGO_HOST", "mongodb")
MONGO_PORT = int(env("MONGO_PORT", "27017"))
MONGO_DATABASE = env("MONGO_DATABASE", "agent")
MONGO_HISTORY_COLLECTION = env("MONGO_HISTORY_COLLECTION", "event_history")
MONGO_DOCUMENT_COLLECTION = env("MONGO_DOCUMENT_COLLECTION", "documents")
MONGO_MODEL_COLLECTION = env("MONGO_MODEL_COLLECTION", "models")
MONGO_WORKFLOW_COLLECTION = env("MONGO_WORKFLOW_COLLECTION", "workflows")


class SubagentSpec(BaseModel):
    id: str
    name: str
    description: str
    queue: str
    history_collection: str
    worker_status_key: str


class SubagentSettingsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_ids: list[str] = Field(default_factory=list, max_length=MAX_SUBAGENT_DOCUMENTS)


SUBAGENTS: dict[str, SubagentSpec] = {
    "qq": SubagentSpec(
        id="qq",
        name="QQ Agent",
        description="处理 QQ 消息与会话事件",
        queue=env("QQ_AGENT_QUEUE_NAME", "subagent:qq:tasks"),
        history_collection=env("QQ_AGENT_HISTORY_COLLECTION", "subagent_qq_history"),
        worker_status_key=env("QQ_AGENT_WORKER_STATUS_KEY", "subagent:qq:worker:status"),
    ),
}

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
documents: Collection = mongo_client[MONGO_DATABASE][MONGO_DOCUMENT_COLLECTION]


class TerminalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str
    files: list[str] = Field(default_factory=list)


class SystemPromptRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    system_prompt: str


class MaxContextCountRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_context_count: str


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


class ModelRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    provider: str = Field(min_length=1, max_length=120)
    model: str = Field(min_length=1, max_length=200)
    base_url: str = Field(min_length=1, max_length=500)
    api_key: str = Field(default="", max_length=1000)
    enabled: bool = True


model_configs: Collection = mongo_client[MONGO_DATABASE][MONGO_MODEL_COLLECTION]
workflows: Collection = mongo_client[MONGO_DATABASE][MONGO_WORKFLOW_COLLECTION]


class WorkflowRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    version: int = Field(ge=1)
    nodes: list[dict[str, Any]] = Field(min_length=1, max_length=MAX_WORKFLOW_NODES)
    connections: list[dict[str, Any]] = Field(default_factory=list, max_length=MAX_WORKFLOW_CONNECTIONS)


app = FastAPI(title="AAgent WebUI")


@app.on_event("startup")
def create_config_indexes():
    try:
        model_configs.create_index("name", unique=True, name="unique_model_name")
        workflows.create_index("key", unique=True, name="unique_workflow_key")
    except PyMongoError as error:
        logger.error("failed to create configuration indexes: %s", error)


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
        ("POST", "/api/terminal"): (MAX_TERMINAL_BODY_BYTES, "请求体不能超过 16 KB"),
        ("POST", "/api/settings/system-prompt"): (MAX_SETTINGS_BODY_BYTES, "请求体不能超过 512 KB"),
        ("PUT", "/api/events"): (MAX_EVENT_BODY_BYTES, "请求体不能超过 256 KB"),
        ("POST", "/api/models"): (MAX_TERMINAL_BODY_BYTES, "模型配置请求体不能超过 16 KB"),
    }
    body_limit = body_limits.get((request.method, request.url.path))
    if request.method in {"POST", "PUT"} and (
        request.url.path == "/api/documents" or request.url.path.startswith("/api/documents/")
    ):
        body_limit = (MAX_DOCUMENT_BODY_BYTES, "文档请求体不能超过 1 MB")
    if request.method == "PUT" and request.url.path.startswith("/api/models/"):
        body_limit = (MAX_TERMINAL_BODY_BYTES, "模型配置请求体不能超过 16 KB")
    if request.method == "PUT" and request.url.path.startswith("/api/workflows/"):
        body_limit = (MAX_WORKFLOW_BODY_BYTES, "Workflow 请求体不能超过 512 KB")
    if body_limit:
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                limit, error_message = body_limit
                if int(content_length) > limit:
                    return JSONResponse(status_code=400, content={"error": error_message})
            except ValueError:
                pass
    return await call_next(request)


def limit_error(limit: int) -> JSONResponse | None:
    if limit < 1 or limit > 300:
        return JSONResponse(status_code=400, content={"error": "limit must be between 1 and 300"})
    return None


def document_id(value: str) -> ObjectId | JSONResponse:
    try:
        return ObjectId(value)
    except InvalidId:
        return JSONResponse(status_code=400, content={"error": "文档 ID 无效"})


def model_response(document: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(document["_id"]),
        "name": document.get("name", ""),
        "provider": document.get("provider", ""),
        "model": document.get("model", ""),
        "base_url": document.get("base_url", ""),
        "api_key": document.get("api_key", ""),
        "enabled": bool(document.get("enabled", True)),
        "created_at": document.get("created_at"),
        "updated_at": document.get("updated_at"),
    }


def workflow_response(document: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(document["_id"]),
        "key": document.get("key", ""),
        "name": document.get("name", ""),
        "version": document.get("version", 1),
        "nodes": document.get("nodes", []),
        "connections": document.get("connections", []),
        "created_at": document.get("created_at"),
        "updated_at": document.get("updated_at"),
    }


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


def read_worker_status(worker_status_key: str = WORKER_STATUS_KEY) -> tuple[dict[str, Any], str | None]:
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


def worker_stage(worker_status_key: str = WORKER_STATUS_KEY) -> tuple[dict[str, Any], str, str | None, dict[str, Any] | None, str]:
    status, warning = read_worker_status(worker_status_key)
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


def pending_stage(limit: int, queue_name: str = QUEUE_NAME) -> tuple[list[dict[str, Any]], int, str, str | None]:
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
    limit: int, running_fingerprint: str, history_collection: Collection = history
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
    limit: int,
    queue_name: str = QUEUE_NAME,
    history_collection: Collection = history,
    worker_status_key: str = WORKER_STATUS_KEY,
) -> dict[str, Any]:
    worker, worker_source, worker_warning, running_item, running_fingerprint = worker_stage(worker_status_key)
    pending_items, pending_count, redis_source, redis_warning = pending_stage(limit, queue_name)
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


def subagent_spec(agent_id: str) -> SubagentSpec | JSONResponse:
    spec = SUBAGENTS.get(agent_id)
    if spec is None:
        return JSONResponse(status_code=404, content={"error": "子 Agent 不存在"})
    return spec


def subagent_settings_key(agent_id: str) -> str:
    return f"subagent:{agent_id}:settings"


def selected_document_ids(agent_id: str) -> list[str]:
    raw = redis_client.get(subagent_settings_key(agent_id))
    if not raw:
        return []
    try:
        value = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return []
    document_ids = value.get("document_ids", []) if isinstance(value, dict) else []
    return [item for item in document_ids if isinstance(item, str)]


@app.get("/api/subagents")
def list_subagents():
    items = []
    for spec in SUBAGENTS.values():
        snapshot = event_snapshot(
            1,
            queue_name=spec.queue,
            history_collection=mongo_client[MONGO_DATABASE][spec.history_collection],
            worker_status_key=spec.worker_status_key,
        )
        items.append(
            {
                "id": spec.id,
                "name": spec.name,
                "description": spec.description,
                "queue": spec.queue,
                "history_collection": spec.history_collection,
                "worker_status_key": spec.worker_status_key,
                "summary": snapshot["summary"],
                "worker": snapshot["worker"],
                "sources": snapshot["sources"],
            }
        )
    return {"items": items}


@app.get("/api/subagents/{agent_id}/events")
def subagent_events(agent_id: str, limit: int = Query(150)):
    error = limit_error(limit)
    if error:
        return error
    spec = subagent_spec(agent_id)
    if isinstance(spec, JSONResponse):
        return spec
    snapshot = event_snapshot(
        limit,
        queue_name=spec.queue,
        history_collection=mongo_client[MONGO_DATABASE][spec.history_collection],
        worker_status_key=spec.worker_status_key,
    )
    snapshot["agent"] = {"id": spec.id, "name": spec.name, "description": spec.description}
    return snapshot


@app.get("/api/subagents/{agent_id}/settings")
def get_subagent_settings(agent_id: str):
    spec = subagent_spec(agent_id)
    if isinstance(spec, JSONResponse):
        return spec
    try:
        return {"document_ids": selected_document_ids(agent_id)}
    except redis.RedisError as error:
        return JSONResponse(status_code=503, content={"error": str(error)})


@app.put("/api/subagents/{agent_id}/settings")
def update_subagent_settings(agent_id: str, payload: SubagentSettingsRequest):
    spec = subagent_spec(agent_id)
    if isinstance(spec, JSONResponse):
        return spec
    unique_ids = list(dict.fromkeys(payload.document_ids))
    try:
        object_ids = [ObjectId(document_id) for document_id in unique_ids]
    except InvalidId:
        return JSONResponse(status_code=400, content={"error": "文档 ID 无效"})
    try:
        existing_ids = {str(item["_id"]) for item in documents.find({"_id": {"$in": object_ids}}, {"_id": 1})}
        missing_ids = [document_id for document_id in unique_ids if document_id not in existing_ids]
        if missing_ids:
            return JSONResponse(status_code=400, content={"error": "包含不存在的文档", "document_ids": missing_ids})
        settings = {"document_ids": unique_ids}
        redis_client.set(subagent_settings_key(agent_id), json.dumps(settings, ensure_ascii=False))
        return settings
    except (redis.RedisError, PyMongoError) as error:
        return JSONResponse(status_code=503, content={"error": str(error)})


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


UPDATE_PENDING_SCRIPT = """
local current = redis.call('LINDEX', KEYS[1], -tonumber(ARGV[1]))
if not current then return 0 end
if current ~= ARGV[2] then return -1 end
redis.call('LSET', KEYS[1], -tonumber(ARGV[1]), ARGV[3])
return 1
"""


@app.put("/api/events")
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
            raw = redis_client.lindex(QUEUE_NAME, -payload.position)
        except redis.RedisError:
            return JSONResponse(status_code=503, content={"error": "Redis 队列暂时不可用"})
        if raw is None:
            return JSONResponse(status_code=404, content={"error": "队列事件不存在或已被处理"})
        if event_fingerprint(decode_queue_event(raw)) != payload.fingerprint:
            return JSONResponse(status_code=409, content={"error": "队列已发生变化，请刷新后重试"})
        try:
            updated = redis_client.eval(UPDATE_PENDING_SCRIPT, 1, QUEUE_NAME, str(payload.position), raw, encoded)
        except redis.RedisError:
            return JSONResponse(status_code=503, content={"error": "Redis 队列暂时不可用"})
        if updated == -1:
            return JSONResponse(status_code=409, content={"error": "队列已发生变化，请刷新后重试"})
        if updated == 0:
            return JSONResponse(status_code=404, content={"error": "队列事件不存在或已被处理"})
        return {"updated": True, "status": "pending", "position": payload.position, "fingerprint": event_fingerprint(event)}

    return JSONResponse(status_code=400, content={"error": "不支持修改该状态的事件"})


@app.get("/api/settings")
def settings():
    try:
        raw = redis_client.get(SETTINGS_KEY)
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


@app.post("/api/settings/max-context-count", status_code=202)
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


@app.get("/api/models")
def list_models():
    try:
        items = model_configs.find({}).sort("updated_at", DESCENDING)
        return {"items": [model_response(item) for item in items]}
    except PyMongoError:
        return JSONResponse(status_code=503, content={"error": "模型配置暂时不可用"})


@app.get("/api/tools")
def list_tools():
    try:
        schemas = redis_client.hgetall(TOOLS_KEY)
    except redis.RedisError:
        return JSONResponse(status_code=503, content={"error": "Tool 注册表暂时不可用"})

    items = []
    for tool_name, raw_schema in schemas.items():
        try:
            schema = json.loads(raw_schema)
        except (TypeError, ValueError):
            logger.warning("ignored invalid tool schema name=%s", tool_name)
            continue
        function_schema = schema.get("function", {}) if isinstance(schema, dict) else {}
        if function_schema.get("name") != tool_name:
            logger.warning("ignored mismatched tool schema name=%s", tool_name)
            continue
        items.append({
            "name": tool_name,
            "description": function_schema.get("description", ""),
            "parameters": function_schema.get("parameters", {}),
        })
    items.sort(key=lambda item: item["name"])
    return {"items": items}


@app.post("/api/models", status_code=201)
def create_model(payload: ModelRequest):
    values = payload.model_dump()
    values["name"] = values["name"].strip()
    values["provider"] = values["provider"].strip()
    values["model"] = values["model"].strip()
    values["base_url"] = values["base_url"].strip().rstrip("/")
    if not all(values[field] for field in ("name", "provider", "model", "base_url")):
        return JSONResponse(status_code=400, content={"error": "模型名称、厂商、模型标识和 Base URL 不能为空"})
    now = datetime.now(timezone.utc)
    values.update({"created_at": now, "updated_at": now})
    try:
        if model_configs.find_one({"name": values["name"]}, {"_id": 1}):
            return JSONResponse(status_code=409, content={"error": "模型名称已存在"})
        result = model_configs.insert_one(values)
    except DuplicateKeyError:
        return JSONResponse(status_code=409, content={"error": "模型名称已存在"})
    except PyMongoError:
        return JSONResponse(status_code=503, content={"error": "暂时无法创建模型配置"})
    values["_id"] = result.inserted_id
    return model_response(values)


@app.put("/api/models/{model_id_value}")
def update_model(model_id_value: str, payload: ModelRequest):
    object_id = document_id(model_id_value)
    if isinstance(object_id, JSONResponse):
        return object_id
    values = payload.model_dump()
    values["name"] = values["name"].strip()
    values["provider"] = values["provider"].strip()
    values["model"] = values["model"].strip()
    values["base_url"] = values["base_url"].strip().rstrip("/")
    if not all(values[field] for field in ("name", "provider", "model", "base_url")):
        return JSONResponse(status_code=400, content={"error": "模型名称、厂商、模型标识和 Base URL 不能为空"})
    values["updated_at"] = datetime.now(timezone.utc)
    try:
        if model_configs.find_one({"name": values["name"], "_id": {"$ne": object_id}}, {"_id": 1}):
            return JSONResponse(status_code=409, content={"error": "模型名称已存在"})
        document = model_configs.find_one_and_update(
            {"_id": object_id},
            {"$set": values},
            return_document=True,
        )
    except DuplicateKeyError:
        return JSONResponse(status_code=409, content={"error": "模型名称已存在"})
    except PyMongoError:
        return JSONResponse(status_code=503, content={"error": "暂时无法保存模型配置"})
    if document is None:
        return JSONResponse(status_code=404, content={"error": "模型配置不存在或已被删除"})
    return model_response(document)


@app.delete("/api/models/{model_id_value}")
def delete_model(model_id_value: str):
    object_id = document_id(model_id_value)
    if isinstance(object_id, JSONResponse):
        return object_id
    try:
        result = model_configs.delete_one({"_id": object_id})
    except PyMongoError:
        return JSONResponse(status_code=503, content={"error": "暂时无法删除模型配置"})
    if result.deleted_count == 0:
        return JSONResponse(status_code=404, content={"error": "模型配置不存在或已被删除"})
    return {"deleted": True, "id": model_id_value}


@app.put("/api/workflows/{workflow_key}")
def upsert_workflow(workflow_key: str, payload: WorkflowRequest):
    key = workflow_key.strip()
    if not key or len(key) > 120 or not all(character.isalnum() or character in {"-", "_"} for character in key):
        return JSONResponse(status_code=400, content={"error": "Workflow key 只能包含字母、数字、连字符和下划线"})
    if not payload.name.strip():
        return JSONResponse(status_code=400, content={"error": "Workflow 名称不能为空"})

    node_ids = [node.get("id") for node in payload.nodes]
    if any(not isinstance(node_id, str) or not node_id for node_id in node_ids):
        return JSONResponse(status_code=400, content={"error": "每个节点都必须包含有效的 id"})
    if len(node_ids) != len(set(node_ids)):
        return JSONResponse(status_code=400, content={"error": "Workflow 中存在重复的节点 id"})
    node_id_set = set(node_ids)
    for connection in payload.connections:
        if connection.get("fromId") not in node_id_set or connection.get("toId") not in node_id_set:
            return JSONResponse(status_code=400, content={"error": "连接引用了不存在的节点"})

    valid_node_types = {"input", "router", "construct_message", "construct_content", "construct_list", "foreach", "llm", "tool"}
    if any(node.get("type") not in valid_node_types for node in payload.nodes):
        return JSONResponse(status_code=400, content={"error": "Workflow 包含不支持的节点类型"})

    tool_nodes = [node for node in payload.nodes if node.get("type") == "tool"]
    if tool_nodes:
        try:
            registered_tool_names = set(redis_client.hkeys(TOOLS_KEY))
        except redis.RedisError:
            return JSONResponse(status_code=503, content={"error": "暂时无法校验 Tool 注册表"})
        if any(node.get("tool") not in registered_tool_names for node in tool_nodes):
            return JSONResponse(status_code=400, content={"error": "Tool 节点引用了未注册的工具"})
        try:
            schemas = redis_client.hmget(TOOLS_KEY, [node.get("tool") for node in tool_nodes])
            tool_properties = {
                node.get("tool"): set(json.loads(raw).get("function", {}).get("parameters", {}).get("properties", {}))
                for node, raw in zip(tool_nodes, schemas)
                if raw
            }
        except (redis.RedisError, TypeError, ValueError):
            return JSONResponse(status_code=503, content={"error": "暂时无法读取 Tool 参数定义"})
        for node in tool_nodes:
            parameters = node.get("parameters", [])
            if not isinstance(parameters, list) or set(parameters) != tool_properties.get(node.get("tool"), set()):
                return JSONResponse(status_code=400, content={"error": "Tool 节点参数端口与工具定义不一致"})
    llm_nodes = [node for node in payload.nodes if node.get("type") == "llm"]
    try:
        model_ids = [ObjectId(node.get("model", "")) for node in llm_nodes]
    except (InvalidId, TypeError):
        return JSONResponse(status_code=400, content={"error": "LLM 节点必须选择有效的模型配置"})
    try:
        available_model_ids = {
            item["_id"] for item in model_configs.find({"_id": {"$in": model_ids}, "enabled": True}, {"_id": 1})
        }
    except PyMongoError:
        return JSONResponse(status_code=503, content={"error": "暂时无法校验模型配置"})
    if any(model_id not in available_model_ids for model_id in model_ids):
        return JSONResponse(status_code=400, content={"error": "LLM 节点引用了不存在或已停用的模型配置"})

    now = datetime.now(timezone.utc)
    values = payload.model_dump()
    values["name"] = values["name"].strip()
    values["updated_at"] = now
    try:
        document = workflows.find_one_and_update(
            {"key": key},
            {"$set": values, "$setOnInsert": {"key": key, "created_at": now}},
            upsert=True,
            return_document=True,
        )
    except PyMongoError:
        return JSONResponse(status_code=503, content={"error": "暂时无法保存 Workflow"})
    return workflow_response(document)


app.include_router(create_documents_router(documents))

static_directory = Path(__file__).parent / "static"


class RevalidatingStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope: dict[str, Any]):
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-cache"
        return response


app.mount("/", RevalidatingStaticFiles(directory=static_directory, html=True), name="static")

logger.info("event console configured address=%s queue=%s", REDIS_ADDRESS, QUEUE_NAME)
