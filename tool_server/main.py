import asyncio
import json
import logging
import uuid
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, AsyncIterator

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from jsonschema import Draft202012Validator, SchemaError, ValidationError
from pydantic import ValidationError as PydanticValidationError
from redis.asyncio import Redis
from redis.exceptions import RedisError

from models import ProviderEvent, RegisterMessage, ToolCallRequest
from provider_registry import ProviderConnection, ProviderRegistry
from settings import Settings
from task_store import TERMINAL_STATUSES, TaskStore, utc_now


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("aagent.tool_server")

settings = Settings.from_env()
redis = Redis.from_url(settings.redis_url, decode_responses=True)
store = TaskStore(redis, settings.task_ttl_seconds)
registry = ProviderRegistry()
CALLBACK_STATUSES = {"working", "completed", "failed"}


def callback_event(task: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any] | None:
    callback = task.get("callback")
    if not callback or patch["status"] not in callback.get("on", CALLBACK_STATUSES):
        return None
    return {
        "queue": callback["queue"],
        "event": {
            "event_type": callback["event_type"],
            "payload": {
                "task_id": task["task_id"],
                "tool": task["tool"],
                "status": patch["status"],
                "result": patch.get("result"),
                "error": patch.get("error"),
                "progress": patch.get("progress"),
                "message": patch.get("message"),
            },
        },
    }


async def transition_terminal(task: dict[str, Any], patch: dict[str, Any]) -> None:
    await store.transition(
        task["task_id"],
        {"pending", "working"},
        patch,
        callback_event(task, patch),
    )


async def handle_provider_event(connection: ProviderConnection, event: ProviderEvent) -> None:
    if event.type == "ping":
        await connection.outgoing.put({"type": "pong"})
        return
    if event.type == "pong":
        return
    if not event.task_id:
        raise ValueError("task_id is required")

    task = await store.get(event.task_id)
    if task is None:
        logger.warning("provider event for missing task task_id=%s", event.task_id)
        return
    if task.get("provider_id") != connection.provider_id:
        raise ValueError("task does not belong to provider")

    if event.type == "accepted":
        patch = {"status": "working"}
        await store.transition(event.task_id, {"pending"}, patch, callback_event(task, patch))
    elif event.type == "rejected":
        await store.transition(
            event.task_id,
            {"pending"},
            {"status": "pending", "provider_id": None, "message": event.message or "provider rejected task"},
        )
    elif event.type == "status":
        if event.status != "working":
            raise ValueError("provider status must be working")
        patch = {"status": "working", "progress": event.progress, "message": event.message}
        await store.transition(event.task_id, {"working"}, patch, callback_event(task, patch))
    elif event.type == "result":
        if event.success is None:
            raise ValueError("result.success is required")
        if event.success:
            tool = await registry.get_tool(task["tool"])
            if tool and tool.outputSchema:
                Draft202012Validator(tool.outputSchema).validate(event.output)
            await transition_terminal(task, {"status": "completed", "result": event.output, "error": None})
        else:
            await transition_terminal(task, {"status": "failed", "result": None, "error": event.error})


async def callback_worker() -> None:
    outbox = "tool:callback:outbox"
    processing = "tool:callback:processing"
    stranded = await redis.lrange(processing, 0, -1)
    if stranded:
        pipeline = redis.pipeline(transaction=True)
        for item in stranded:
            pipeline.lpush(outbox, item)
        pipeline.delete(processing)
        await pipeline.execute()

    while True:
        item = await redis.brpoplpush(outbox, processing, timeout=5)
        if item is None:
            continue
        try:
            record = json.loads(item)
            await redis.lpush(record["queue"], json.dumps(record["event"], ensure_ascii=False))
            await redis.lrem(processing, 1, item)
        except (KeyError, TypeError, ValueError, RedisError):
            logger.exception("callback delivery failed")
            pipeline = redis.pipeline(transaction=True)
            pipeline.lrem(processing, 1, item)
            pipeline.lpush(outbox, item)
            await pipeline.execute()
            await asyncio.sleep(1)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    worker = asyncio.create_task(callback_worker())
    try:
        yield
    finally:
        worker.cancel()
        with suppress(asyncio.CancelledError):
            await worker
        await redis.aclose()


app = FastAPI(title="AAgent Tool Server", lifespan=lifespan)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["Content-Security-Policy"] = "default-src 'self'; style-src 'self'; script-src 'self'; connect-src 'self'; img-src 'self' data:"
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


@app.get("/api/health")
async def health():
    try:
        await redis.ping()
    except RedisError as error:
        return JSONResponse(status_code=503, content={"status": "unavailable", "error": str(error)})
    return {"status": "ok"}


@app.get("/api/tools")
async def list_tools():
    return {"tools": await registry.list_tools()}


@app.get("/api/overview")
async def overview(limit: int = 100):
    bounded_limit = max(1, min(limit, 200))
    providers, tools, tasks = await asyncio.gather(
        registry.list_providers(),
        registry.list_tools(),
        store.list_recent(bounded_limit),
    )
    status_counts = {status: 0 for status in ["pending", "working", "completed", "failed"]}
    for task in tasks:
        if task["status"] in status_counts:
            status_counts[task["status"]] += 1
    return {
        "providers": providers,
        "tools": tools,
        "tasks": tasks,
        "summary": {
            "providers": len(providers),
            "tools": len(tools),
            "tasks": len(tasks),
            "statuses": status_counts,
        },
        "fetched_at": utc_now(),
    }


@app.get("/api/tools/{tool_name}")
async def get_tool(tool_name: str):
    tool = await registry.get_tool(tool_name)
    if tool is None:
        raise HTTPException(status_code=404, detail="tool not found")
    return tool


@app.post("/api/tools/{tool_name}/calls")
async def call_tool(tool_name: str, request: ToolCallRequest):
    tool = await registry.get_tool(tool_name)
    if tool is None:
        raise HTTPException(status_code=503, detail="tool provider is unavailable")
    if request.callback and request.callback.event_type not in settings.callback_event_types:
        raise HTTPException(status_code=400, detail="callback event type is not allowed")
    try:
        Draft202012Validator.check_schema(tool.inputSchema)
        Draft202012Validator(tool.inputSchema).validate(request.arguments)
    except (SchemaError, ValidationError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    task_id = uuid.uuid4().hex
    now = datetime.now(timezone.utc)
    task = {
        "task_id": task_id,
        "tool": tool_name,
        "provider_id": None,
        "status": "pending",
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
        "expires_at": (now + timedelta(seconds=settings.task_ttl_seconds)).isoformat(),
        "result": None,
        "error": None,
        "callback": request.callback.model_dump() if request.callback else None,
    }
    if not await store.create(task):
        raise HTTPException(status_code=409, detail="task id collision")

    tools = await registry.list_tools()
    provider_id = next(item["provider_id"] for item in tools if item["name"] == tool_name)
    await store.transition(task_id, {"pending"}, {"status": "pending", "provider_id": provider_id})
    dispatched = await registry.send(
        tool_name,
        {
            "type": "invoke",
            "task_id": task_id,
            "tool": tool_name,
            "arguments": request.arguments,
            "deadline": (now + timedelta(milliseconds=request.timeout_ms)).isoformat(),
        },
    )
    if not dispatched:
        await store.transition(task_id, {"pending"}, {"status": "pending", "provider_id": None})

    if request.mode == "async" or not dispatched:
        current = await store.get(task_id)
        return JSONResponse(status_code=202, content=current)

    timeout_ms = min(request.timeout_ms, settings.max_wait_ms)
    final = await store.wait_for_terminal(task_id, timeout_ms / 1000)
    return JSONResponse(status_code=200 if final and final["status"] in TERMINAL_STATUSES else 202, content=final)


@app.get("/api/tasks/{task_id}")
async def get_task(task_id: str):
    task = await store.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    return task


@app.websocket("/ws/providers")
async def provider_socket(websocket: WebSocket):
    await websocket.accept()
    connection: ProviderConnection | None = None
    try:
        raw = await asyncio.wait_for(websocket.receive_json(), timeout=10)
        registration = RegisterMessage.model_validate(raw)
        for tool in registration.tools:
            Draft202012Validator.check_schema(tool.inputSchema)
            if tool.outputSchema:
                Draft202012Validator.check_schema(tool.outputSchema)
        connection = await registry.register(registration, websocket)
        await connection.outgoing.put({"type": "registered", "provider_id": registration.provider_id})
        await redis.hset(
            "tool:providers",
            registration.provider_id,
            json.dumps(registration.model_dump(), ensure_ascii=False),
        )
        while True:
            event = ProviderEvent.model_validate(await websocket.receive_json())
            await handle_provider_event(connection, event)
    except (PydanticValidationError, SchemaError, ValueError) as error:
        await websocket.close(code=1008, reason=str(error)[:120])
    except (WebSocketDisconnect, asyncio.TimeoutError):
        pass
    finally:
        if connection:
            await registry.unregister(connection)
            await redis.hdel("tool:providers", connection.provider_id)


static_directory = Path(__file__).parent / "static"
app.mount("/", StaticFiles(directory=static_directory, html=True), name="static")