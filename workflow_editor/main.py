import logging
import json
import os
import time
from pathlib import Path
from typing import Any

import redis
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pymongo import DESCENDING, MongoClient
from pymongo.errors import PyMongoError

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("aagent.workflow_editor")


app = FastAPI(title="AAgent Workflow Editor")


def env(name: str, fallback: str) -> str:
    return os.getenv(name) or fallback


redis_address = os.getenv("REDIS_ADDR") or f"{env('REDIS_HOST', 'redis')}:{env('REDIS_PORT', '6379')}"
redis_client = redis.Redis.from_url(
    f"redis://{redis_address}/{int(env('REDIS_DB', '0'))}",
    password=os.getenv("REDIS_PASSWORD") or None,
    decode_responses=True,
    socket_connect_timeout=5,
    socket_timeout=5,
)
mongo_options: dict[str, Any] = {
    "host": env("MONGO_HOST", "mongodb"),
    "port": int(env("MONGO_PORT", "27017")),
    "serverSelectionTimeoutMS": 5000,
    "tz_aware": True,
}
if os.getenv("MONGO_USER"):
    mongo_options.update(
        username=os.environ["MONGO_USER"],
        password=os.getenv("MONGO_PASS", ""),
        authSource="admin",
    )
database = MongoClient(**mongo_options)[env("MONGO_DATABASE", "agent")]
models = database[env("MONGO_MODEL_COLLECTION", "models")]
tools_key = env("AGENT_TOOLS_KEY", "aagent:tools")


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["Content-Security-Policy"] = "default-src 'self'; style-src 'self'; script-src 'self'; connect-src 'self'; img-src 'self' data:"
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
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


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/models")
def list_models():
    try:
        items = models.find({"enabled": {"$ne": False}}, {"name": 1, "model": 1, "provider": 1}).sort("updated_at", DESCENDING)
        return {
            "items": [
                {
                    "id": str(item["_id"]),
                    "name": item.get("name", ""),
                    "model": item.get("model", ""),
                    "provider": item.get("provider", ""),
                    "enabled": True,
                }
                for item in items
            ]
        }
    except PyMongoError:
        return JSONResponse(status_code=503, content={"error": "模型配置暂时不可用"})


@app.get("/api/tools")
def list_tools():
    try:
        schemas = redis_client.hgetall(tools_key)
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
        items.append(
            {
                "name": tool_name,
                "description": function_schema.get("description", ""),
                "parameters": function_schema.get("parameters", {}),
            }
        )
    items.sort(key=lambda item: item["name"])
    return {"items": items}


static_directory = Path(__file__).parent / "static"
app.mount("/", StaticFiles(directory=static_directory, html=True), name="static")