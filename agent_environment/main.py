import json
import logging
import os
import time
from typing import Any

import redis
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.errors import PyMongoError

from file_store import FileStore, FileStoreUnavailableError
from files import create_files_router
from terminal import create_terminal_router
from processes import create_processes_router
from workflow_logs import create_workflow_logs_router
from process_logs import create_process_logs_router
from scheduler import create_scheduler_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("aagent.environment")

MAX_TERMINAL_BODY_BYTES = 1024 * 1024
MAX_PROCESS_BODY_BYTES = 256 * 1024
MAX_FILE_BODY_BYTES = 128 * 1024 * 1024


def env(name: str, fallback: str) -> str:
    return os.getenv(name) or fallback


def redis_address() -> str:
    explicit = os.getenv("REDIS_ADDR")
    if explicit:
        return explicit
    return f"{env('REDIS_HOST', 'redis')}:{env('REDIS_PORT', '6379')}"


REDIS_ADDRESS = redis_address()
REDIS_DB = int(env("REDIS_DB", "0"))
REDIS_KERNEL_DB = int(env("REDIS_KERNEL_DB", "1"))
MONGO_HOST = env("MONGO_HOST", "mongodb")
MONGO_PORT = int(env("MONGO_PORT", "27017"))
MONGO_DATABASE = env("MONGO_DATABASE", "agent")
MONGO_TERMINAL_COLLECTION = env("MONGO_TERMINAL_COLLECTION", "terminal_messages")
MONGO_WORKFLOW_LOG_COLLECTION = env("MONGO_WORKFLOW_LOG_COLLECTION", "workflow_logs")
MONGO_PROCESS_LOG_COLLECTION = env("MONGO_PROCESS_LOG_COLLECTION", "process_logs")
MONGO_FILE_EVENT_COLLECTION = env("MONGO_FILE_EVENT_COLLECTION", "workspace_file_events")
MONGO_WORKSPACE_FILE_COLLECTION = env("MONGO_WORKSPACE_FILE_COLLECTION", "workspace_files")

redis_client = redis.Redis.from_url(
    f"redis://{REDIS_ADDRESS}/{REDIS_DB}",
    password=os.getenv("REDIS_PASSWORD") or None,
    decode_responses=True,
    socket_connect_timeout=5,
    socket_timeout=5,
)
kernel_redis_client = redis.Redis.from_url(
    f"redis://{REDIS_ADDRESS}/{REDIS_KERNEL_DB}",
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
terminal_messages: Collection = database[MONGO_TERMINAL_COLLECTION]
workflow_logs: Collection = database[MONGO_WORKFLOW_LOG_COLLECTION]
process_logs: Collection = database[MONGO_PROCESS_LOG_COLLECTION]
file_events: Collection = database[MONGO_FILE_EVENT_COLLECTION]
workspace_files: Collection = database[MONGO_WORKSPACE_FILE_COLLECTION]
file_store = FileStore(file_events, workspace_files)

app = FastAPI(title="AAgent Environment")


@app.exception_handler(FileStoreUnavailableError)
def file_store_unavailable(_, error: FileStoreUnavailableError):
    logger.error("workspace file store unavailable: %s", error)
    return JSONResponse(status_code=503, content={"error": "workspace file store unavailable"})


@app.on_event("startup")
def create_terminal_indexes():
    try:
        terminal_messages.create_index(
            [("created_at", -1), ("_id", -1)], name="terminal_created_at_id"
        )
        terminal_messages.create_index(
            [("terminal_id", 1), ("created_at", -1), ("_id", -1)],
            name="terminal_id_created_at_id",
        )
        terminal_messages.create_index(
            [("terminal_id", 1), ("role", 1), ("_id", 1)],
            name="terminal_id_role_id",
        )
    except PyMongoError as error:
        logger.error("failed to create terminal indexes: %s", error)


@app.on_event("startup")
def create_scheduler_indexes():
    try:
        process_logs.create_index([("start_time", -1)], name="process_start_time")
        process_logs.create_index([("status", 1), ("start_time", -1)], name="process_status_start_time")
        process_logs.create_index([("finished_at", 1)], name="process_finished_at")
    except PyMongoError as error:
        logger.error("failed to create scheduler indexes: %s", error)


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
        ("POST", "/api/processes"): (MAX_PROCESS_BODY_BYTES, "请求体不能超过 256 KB"),
        ("POST", "/api/terminal"): (MAX_TERMINAL_BODY_BYTES, "终端请求体不能超过 1 MiB"),
    }
    body_limit = body_limits.get((request.method, request.url.path))
    if request.method in {"POST", "PUT"} and (
        request.url.path == "/api/files" or request.url.path.startswith("/api/files/")
    ):
        body_limit = (MAX_FILE_BODY_BYTES, "文件请求体不能超过 128 MB")
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
        kernel_redis_client.ping()
        mongo_client.admin.command("ping")
        file_store.revision
    except (redis.RedisError, PyMongoError, FileStoreUnavailableError):
        logger.exception("environment dependencies unavailable")
        return JSONResponse(status_code=503, content={"status": "unavailable"})
    return {"status": "ok"}


app.include_router(create_terminal_router(redis_client, terminal_messages))
app.include_router(create_processes_router(redis_client, file_store))
app.include_router(create_workflow_logs_router(workflow_logs))
app.include_router(create_process_logs_router(process_logs))
app.include_router(create_scheduler_router(process_logs, redis_client))


def lookup_process(process_id: str):
    raw = kernel_redis_client.hget(env("ProcessTable", "processtable"), process_id)
    return None if raw is None else json.loads(raw)


app.include_router(create_files_router(file_store, lookup_process))

