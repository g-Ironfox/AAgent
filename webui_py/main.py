import logging
import os
import time
from pathlib import Path
from typing import Any

import redis
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.errors import PyMongoError

from documents import create_documents_router
from events import create_events_router
from models import create_models_router
from settings import create_settings_router
from subagents import SubagentSpec, create_subagents_router
from workflows import create_workflows_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("aagent.webui")

MAX_TERMINAL_BODY_BYTES = 16 * 1024
MAX_SETTINGS_BODY_BYTES = 512 * 1024
MAX_EVENT_BODY_BYTES = 256 * 1024
MAX_DOCUMENT_BODY_BYTES = 1024 * 1024
MAX_WORKFLOW_BODY_BYTES = 512 * 1024


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
database = mongo_client[MONGO_DATABASE]
history: Collection = database[MONGO_HISTORY_COLLECTION]
documents: Collection = database[MONGO_DOCUMENT_COLLECTION]
model_configs: Collection = database[MONGO_MODEL_COLLECTION]
workflows: Collection = database[MONGO_WORKFLOW_COLLECTION]

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
        logger.info(
            "request method=%s path=%s duration=%.3fs",
            request.method,
            request.url.path,
            time.perf_counter() - started,
        )
    return response


@app.middleware("http")
async def request_body_guard(request: Request, call_next):
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


@app.get("/api/health")
def health():
    try:
        redis_client.ping()
    except redis.RedisError as error:
        return JSONResponse(status_code=503, content={"status": "unavailable", "error": str(error)})
    return {"status": "ok"}


app.include_router(create_events_router(redis_client, history, QUEUE_NAME, WORKER_STATUS_KEY))
app.include_router(create_settings_router(redis_client, SETTINGS_KEY, QUEUE_NAME))
app.include_router(create_models_router(model_configs))
app.include_router(create_workflows_router(redis_client, TOOLS_KEY, model_configs, workflows))
app.include_router(create_subagents_router(redis_client, database, documents, SUBAGENTS))
app.include_router(create_documents_router(documents))

static_directory = Path(__file__).parent / "static"


class RevalidatingStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope: dict[str, Any]):
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-cache"
        return response


app.mount("/", RevalidatingStaticFiles(directory=static_directory, html=True), name="static")
