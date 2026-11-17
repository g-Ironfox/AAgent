"""Create runnable workflow processes from workspace files."""
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from pymongo.errors import PyMongoError
from redis.exceptions import RedisError

from file_store import FileMissingError

# The same runtime modules are used locally and in the WebUI image.
_RUNTIME_PATH = Path(os.getenv("AGENT_RUNTIME_PATH", Path(__file__).resolve().parent.parent / "agent"))
if str(_RUNTIME_PATH) not in sys.path:
    sys.path.append(str(_RUNTIME_PATH))
from process_creation import build_workflow_process, initialize_process_pair
from r import BLOCKED_PROCESSES, PROCESSTABLE, READY_PROCESSES

logger = logging.getLogger(__name__)


class CreateProcessRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workflow_file_id: str = Field(min_length=1, max_length=200)
    inputs: dict[str, Any] = Field(default_factory=dict)


def create_processes_router(redis_client, store, process_logs) -> APIRouter:
    router = APIRouter()

    @router.post("/api/processes", status_code=201)
    def create_process(request: CreateProcessRequest):
        try:
            file = store.get_file(request.workflow_file_id)
        except FileMissingError:
            return JSONResponse(status_code=404, content={"error": "工作流文件不存在"})
        try:
            document = json.loads(file["content"])
            if not isinstance(document, dict):
                raise ValueError("工作流文件必须是 JSON 对象")
            process = build_workflow_process(document, request.inputs, request.workflow_file_id)
            terminal = initialize_process_pair(process)
            records = {
                item["process_id"]: json.dumps(item, ensure_ascii=False, allow_nan=False)
                for item in (process, terminal)
            }
        except (ValueError, TypeError, KeyError) as error:
            return JSONResponse(status_code=400, content={"error": str(error)})

        try:
            # Publish the complete pair and ready entry together before a worker can pop it.
            with redis_client.pipeline(transaction=True) as transaction:
                transaction.hset(PROCESSTABLE, mapping=records)
                transaction.srem(BLOCKED_PROCESSES, process["process_id"])
                transaction.lpush(READY_PROCESSES, process["process_id"])
                transaction.execute()
        except RedisError:
            logger.exception("failed to create process")
            return JSONResponse(status_code=503, content={"error": "进程创建失败，Redis 暂不可用"})

        try:
            process_logs.update_one(
                {"process_id": process["process_id"]},
                {"$setOnInsert": {
                    "process_id": process["process_id"],
                    "start_time": datetime.fromisoformat(process["start_time"]),
                    "nodes": [],
                    "status": "running",
                }},
                upsert=True,
            )
        except PyMongoError:
            # The process is already scheduled; report success even if timing storage is unavailable.
            logger.exception("failed to initialize process timing for %s", process["process_id"])
        return {key: process[key] for key in (
            "process_id", "parent_process_id", "terminal_process_id", "start_time", "status", "workflow_name"
        )}

    return router
