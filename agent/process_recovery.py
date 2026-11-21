"""Close durable observations whose runtime records were lost before startup."""
import json
from datetime import datetime, timezone

from pymongo import ReturnDocument

from process_repository import PROCESSTABLE, TERMINAL_INDEX, TERMINAL_SESSIONS, TERMINAL_STATUSES
from redis_client import REDIS_KERNEL_DB, REDIS_PUBLIC_DB
from workflow_run_repository import record_process_workflow_run

LOSS_REASON = "runtime_state_lost"


def _iso(value):
    return value.isoformat() if isinstance(value, datetime) else value


def _start_time(process):
    value = process.get("start_time")
    if value is None:
        return datetime.min.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def _finalize_lost_process(client, process, records, recovered):
    """Replay derived records even if a previous recovery stopped halfway through."""
    if process.get("process_type", "workflow") == "workflow" and process.get("workflow_name"):
        record_process_workflow_run({
            "run_id": process.get("invocation_id") or process["process_id"],
            "process_id": process["process_id"],
            "parent_process_id": process.get("parent_process_id"),
            "root_process_id": process.get("root_process_id"),
            "workflow_name": process["workflow_name"],
            "call_stack": process.get("call_stack", []),
            "started_at": process.get("start_time"),
            "finished_at": process["finished_at"],
            "duration_ms": None,
            "active_duration_ms": process.get("active_duration_ms", 0),
            "status": "lost",
            "input": process.get("input", {}),
            "output": process.get("output", {}),
            "node_trace": process.get("nodes", []),
            "error": process.get("error"),
        })
    # Child and terminal observations use the root's metadata when available.
    # This keeps a session's name and closure time stable regardless of scan order.
    process = recovered.get(process.get("root_process_id"), process)
    terminal_id = process.get("terminal_id")
    if not terminal_id:
        return
    roots = [p for p in recovered.values() if p.get("terminal_id") == terminal_id
             and p.get("process_type", "workflow") == "workflow"
             and p.get("root_process_id", p["process_id"]) == p["process_id"]]
    if roots:
        process = max(roots, key=_start_time)
    if process.get("root_process_id", process["process_id"]) in records:
        return
    # Keep a surviving active owner or a newer completed run on this terminal.
    if any(record.get("terminal_id") == terminal_id and (
            record.get("status") not in TERMINAL_STATUSES
            or (record.get("process_type", "workflow") == "workflow"
                and record.get("root_process_id", record["process_id"]) == record["process_id"]
                and _start_time(record) >= _start_time(process))) for record in records.values()):
        return
    session = {
        "terminal_id": terminal_id, "status": "closed",
        "start_time": _iso(process.get("start_time")), "closed_at": _iso(process["finished_at"]),
        "workflow_name": process.get("workflow_name"), "workflow_status": "lost", "wait_kind": None,
    }
    with client.pipeline(transaction=True) as pipe:
        pipe.hdel(TERMINAL_INDEX, terminal_id)
        pipe.execute_command("SELECT", REDIS_PUBLIC_DB)
        pipe.hset(TERMINAL_SESSIONS, terminal_id, json.dumps(session, ensure_ascii=False))
        pipe.execute_command("SELECT", REDIS_KERNEL_DB)
        pipe.execute()


def reconcile_lost_processes(client, logs):
    """Run under the single runtime owner before any scheduling or event handling.

    Redis must answer successfully: connection/loading errors are never evidence
    of an empty kernel. finished_at records when the loss was detected.
    """
    records = {pid: json.loads(raw) for pid, raw in client.hgetall(PROCESSTABLE).items()}
    query = {"$or": [
        {"status": {"$nin": sorted(TERMINAL_STATUSES)}, "finished_at": None},
        {"status": "lost"},
    ]}
    recovered = {}
    for process in logs.find(query):
        pid = process.get("process_id")
        # Recheck against Redis before modifying history, rather than relying
        # only on the earlier snapshot used to protect surviving terminal owners.
        if not isinstance(pid, str) or not pid or client.hexists(PROCESSTABLE, pid):
            continue
        if process.get("status") != "lost":
            detected_at = datetime.now(timezone.utc)
            process = logs.find_one_and_update(
                {"_id": process["_id"], "status": process.get("status"),
                 "observed_at": process.get("observed_at"), "finished_at": None},
                {"$set": {"status": "lost", "finished_at": detected_at, "wait_for": None},
                 "$push": {"events": {"event": "lost", "status": "lost",
                                       "timestamp": detected_at.isoformat(), "reason": LOSS_REASON}}},
                return_document=ReturnDocument.AFTER,
            )
            if process is None:  # Another observer changed this record in the meantime.
                continue
        recovered[pid] = process
    for process in recovered.values():
        _finalize_lost_process(client, process, records, recovered)
