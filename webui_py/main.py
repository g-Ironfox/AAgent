import logging
import os
import time
from pathlib import Path
from typing import Any

import redis
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.errors import PyMongoError

from event_bindings import create_event_bindings_router
from file_store import FileStore, FileStoreUnavailableError
from files import create_files_router
from events import create_events_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("aagent.webui")

MAX_TERMINAL_BODY_BYTES = 16 * 1024
MAX_EVENT_BODY_BYTES = 256 * 1024
MAX_FILE_BODY_BYTES = 1024 * 1024


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
MONGO_HOST = env("MONGO_HOST", "mongodb")
MONGO_PORT = int(env("MONGO_PORT", "27017"))
MONGO_DATABASE = env("MONGO_DATABASE", "agent")
MONGO_HISTORY_COLLECTION = env("MONGO_HISTORY_COLLECTION", "event_history")
MONGO_WORKFLOW_COLLECTION = env("MONGO_WORKFLOW_COLLECTION", "workflows")
MONGO_EVENT_BINDING_COLLECTION = env("MONGO_EVENT_BINDING_COLLECTION", "event_bindings")
MONGO_FILE_EVENT_COLLECTION = env("MONGO_FILE_EVENT_COLLECTION", "workspace_file_events")
MONGO_WORKSPACE_FILE_COLLECTION = env("MONGO_WORKSPACE_FILE_COLLECTION", "workspace_files")

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
workflows: Collection = database[MONGO_WORKFLOW_COLLECTION]
event_bindings: Collection = database[MONGO_EVENT_BINDING_COLLECTION]
file_events: Collection = database[MONGO_FILE_EVENT_COLLECTION]
workspace_files: Collection = database[MONGO_WORKSPACE_FILE_COLLECTION]
file_store = FileStore(file_events, workspace_files)

app = FastAPI(title="AAgent WebUI")


@app.exception_handler(FileStoreUnavailableError)
def file_store_unavailable(_, error: FileStoreUnavailableError):
    logger.error("workspace file store unavailable: %s", error)
    return JSONResponse(status_code=503, content={"error": "workspace file store unavailable"})


@app.on_event("startup")
def create_config_indexes():
    try:
        if "unique_event_binding_route" in event_bindings.index_information():
            event_bindings.drop_index("unique_event_binding_route")
        event_bindings.create_index("event_type", unique=True, name="unique_event_binding_type")
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
        ("PUT", "/api/events"): (MAX_EVENT_BODY_BYTES, "请求体不能超过 256 KB"),
    }
    body_limit = body_limits.get((request.method, request.url.path))
    if request.method in {"POST", "PUT"} and (
        request.url.path == "/api/files" or request.url.path.startswith("/api/files/")
    ):
        body_limit = (MAX_FILE_BODY_BYTES, "文件请求体不能超过 1 MB")
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
app.include_router(create_event_bindings_router(event_bindings, workflows))
app.include_router(create_files_router(file_store))

static_directory = Path(__file__).parent / "static"


@app.get("/workspace", include_in_schema=False)
def workspace_page():
    return FileResponse(static_directory / "workspace.html")


@app.get("/workspace/replay", include_in_schema=False)
def workspace_replay_page():
    return FileResponse(static_directory / "replay.html")


@app.get("/workspace.html", include_in_schema=False)
def old_workspace_page_url():
    return RedirectResponse("/workspace", status_code=308)


@app.get("/document.html", include_in_schema=False)
def old_document_page_url():
    return RedirectResponse("/workspace", status_code=308)


class RevalidatingStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope: dict[str, Any]):
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-store" if path.endswith(".html") else "no-cache"
        return response


app.mount("/", RevalidatingStaticFiles(directory=static_directory, html=True), name="static")
