"""Public Redis current state and MongoDB history; never read kernel Redis."""
import json
import os
from collections import Counter
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from pymongo import DESCENDING
from pymongo.errors import PyMongoError
from redis.exceptions import RedisError

FINAL_STATUSES = {"completed", "failed", "terminated", "killed", "lost"}
PROJECTION = {key: 1 for key in (
    "process_id", "process_type", "parent_process_id", "root_process_id",
    "terminal_id", "workflow_name", "status", "start_time", "finished_at",
    "observed_at", "wait_for", "events", "active_duration_ms", "current_node_id",
)}
ACTIVE_LIMIT = 1000
PREFIX = os.getenv("PUBLIC_SCHEDULER_PREFIX", "aagent:scheduler")
PUBLIC_PROCESSES = PREFIX + ":processes"
PUBLIC_META = PREFIX + ":meta"
PUBLIC_TABLES = {status: PREFIX + ":" + status for status in (
    "ready", "running", "blocked", "waiting_for_input",
)}


def _utc(value):
    if value.tzinfo is None:
        raise ValueError("time range must include a timezone")
    return value.astimezone(timezone.utc)


def _serialize(documents):
    return [{key: value for key, value in document.items() if key != "_id"}
            for document in documents]


def _current_snapshot(client):
    # One public-DB transaction makes queue membership and records consistent.
    with client.pipeline(transaction=True) as pipe:
        pipe.hgetall(PUBLIC_PROCESSES)
        pipe.hgetall(PUBLIC_META)
        pipe.lrange(PUBLIC_TABLES["ready"], 0, -1)
        for status in ("running", "blocked", "waiting_for_input"):
            pipe.smembers(PUBLIC_TABLES[status])
        raw, meta, ready, running, blocked, waiting = pipe.execute()
    if not meta.get("updated_at"):
        raise ValueError("public scheduler projection is not initialized; restart the Agent runtime")
    processes = []
    for process_id, value in raw.items():
        process = json.loads(value)
        if (not isinstance(process, dict) or process.get("process_id") != process_id
                or not isinstance(process.get("status"), str)):
            raise ValueError("public scheduler projection contains an invalid process record")
        if process["status"] not in FINAL_STATUSES:
            processes.append(process)
    counts = dict(Counter(process["status"] for process in processes))
    priority = {"running": 0, "ready": 1, "blocked": 2, "waiting_for_input": 3}
    ready_positions = {process_id: index for index, process_id in enumerate(reversed(ready))}
    processes.sort(key=lambda process: (
        priority.get(process["status"], 99),
        ready_positions.get(process["process_id"], len(ready)) if process["status"] == "ready" else 0,
        process.get("start_time") or "", process["process_id"],
    ))
    return {
        "active_items": processes[:ACTIVE_LIMIT], "active_count": len(processes),
        "active_truncated": len(processes) > ACTIVE_LIMIT, "status_counts": counts,
        "process_tables": {"ready": list(reversed(ready)), "running": sorted(running),
                           "blocked": sorted(blocked), "waiting_for_input": sorted(waiting)},
        "current_observed_at": meta["updated_at"], "current_available": True,
    }


def create_scheduler_router(logs, public_redis) -> APIRouter:
    router = APIRouter()

    @router.get("/api/scheduler")
    def scheduler_snapshot(
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = Query(500, ge=1, le=1000),
    ):
        now = datetime.now(timezone.utc)
        try:
            end = _utc(end) if end is not None else now
            start = _utc(start) if start is not None else end - timedelta(minutes=15)
            if start >= end or end - start > timedelta(days=7):
                raise ValueError("time range must be positive and at most 7 days")
            if end > now + timedelta(seconds=5):
                raise ValueError("time range cannot end in the future")
        except ValueError as error:
            return JSONResponse(status_code=422, content={"error": str(error)})
        warnings = []
        result = {
            "fetched_at": now, "start": start, "end": end,
            "items": [], "history_count": 0, "history_truncated": False,
            "history_available": False, "history_source": "process_logs",
            "active_items": [], "active_count": 0, "active_truncated": False,
            "current_available": False, "current_source": "public_redis",
            "status_counts": {}, "process_tables": {}, "current_observed_at": None,
        }
        try:
            result.update(_current_snapshot(public_redis))
        except (RedisError, ValueError, TypeError) as error:
            warnings.append("公开 Redis 进程状态不可用：" + str(error))
        overlap = {
            "start_time": {"$lte": end},
            "$or": [{"finished_at": {"$gte": start}}, {"finished_at": None}],
        }
        try:
            count = logs.count_documents(overlap)
            history = list(logs.find(overlap, PROJECTION)
                           .sort("start_time", DESCENDING).limit(limit))
            result.update(items=_serialize(history), history_count=count,
                          history_truncated=count > len(history), history_available=True)
        except PyMongoError:
            warnings.append("MongoDB 历史日志不可用，甘特图暂时无法加载。")
        if not result["current_available"] and not result["history_available"]:
            return JSONResponse(status_code=503, content={"error": "；".join(warnings)})
        result["warnings"] = warnings
        return result

    return router
