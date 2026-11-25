"""Publish minimal, one-way scheduler state into the public Redis database.

Commands join the kernel's MULTI/EXEC on the same Redis instance. Always restore
its selected database before EXEC completes so pooled connections stay private.
"""
import json
import os
from datetime import datetime, timezone

import redis

from process import Process
from redis_client import REDIS_KERNEL_DB, REDIS_PUBLIC_DB

PREFIX = os.getenv("PUBLIC_SCHEDULER_PREFIX", "aagent:scheduler")
PUBLIC_PROCESSES = PREFIX + ":processes"
PUBLIC_META = PREFIX + ":meta"
PUBLIC_TABLES = {status: PREFIX + ":" + status for status in (
    "ready", "running", "blocked", "waiting_for_input",
)}
FIELDS = (
    "process_id", "process_type", "parent_process_id", "root_process_id",
    "terminal_id", "terminal_process_id", "workflow_name", "status", "start_time",
    "finished_at", "wait_for", "active_duration_ms", "current_node_id",
)


def _encode(process: Process, observed_at: str) -> str:
    result = {key: getattr(process, key) for key in FIELDS}
    result["observed_at"] = observed_at
    return json.dumps(result, ensure_ascii=False, allow_nan=False)


def queue_public_process_updates(pipe, updates: dict[str, Process], *, enqueue_ready=True):
    """Queue committed Process objects into the public scheduler projection."""
    if not updates:
        return
    now = datetime.now(timezone.utc).isoformat()
    encoded = {key: _encode(process, now) for key, process in updates.items()}
    pipe.execute_command("SELECT", REDIS_PUBLIC_DB)
    pipe.hset(PUBLIC_PROCESSES, mapping=encoded)
    for process_id, process in updates.items():
        if enqueue_ready or process.status != "ready":
            pipe.lrem(PUBLIC_TABLES["ready"], 0, process_id)
        for status in ("running", "blocked", "waiting_for_input"):
            pipe.srem(PUBLIC_TABLES[status], process_id)
        if process.status == "ready" and enqueue_ready:
            pipe.lpush(PUBLIC_TABLES[process.status], process_id)
        elif process.status in {"running", "blocked", "waiting_for_input"}:
            pipe.sadd(PUBLIC_TABLES[process.status], process_id)
    pipe.hset(PUBLIC_META, mapping={"updated_at": now})
    pipe.execute_command("SELECT", REDIS_KERNEL_DB)


def rebuild_public_scheduler(client, process_table, ready_queue):
    """Replace the public projection from authoritative kernel state at startup."""
    while True:
        with client.pipeline() as pipe:
            try:
                pipe.watch(process_table, ready_queue)
                records = {key: Process.from_record(json.loads(raw))
                           for key, raw in pipe.hgetall(process_table).items()}
                # Redis uses LPUSH/RPOP, so retain the stored queue order here.
                ready = pipe.lrange(ready_queue, 0, -1)
                now = datetime.now(timezone.utc).isoformat()
                pipe.multi()
                pipe.execute_command("SELECT", REDIS_PUBLIC_DB)
                pipe.delete(PUBLIC_PROCESSES, PUBLIC_META, *PUBLIC_TABLES.values())
                pipe.execute_command("SELECT", REDIS_KERNEL_DB)
                queue_public_process_updates(pipe, records)
                pipe.execute_command("SELECT", REDIS_PUBLIC_DB)
                pipe.delete(PUBLIC_TABLES["ready"])
                for process_id in reversed(ready):
                    if records[process_id].status == "ready":
                        pipe.lpush(PUBLIC_TABLES["ready"], process_id)
                pipe.hset(PUBLIC_META, mapping={"initialized_at": now, "updated_at": now})
                pipe.execute_command("SELECT", REDIS_KERNEL_DB)
                pipe.execute()
                return
            except redis.WatchError:
                continue
