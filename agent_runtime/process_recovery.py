"""Close durable observations whose runtime process records were lost."""
import json
from datetime import datetime, timezone

from pymongo import ReturnDocument

from process import Process, WorkflowProcess, TerminalProcess, TERMINAL_STATUSES
from process_repository import PROCESSTABLE, TERMINAL_INDEX, TERMINAL_SESSIONS
from redis_client import REDIS_KERNEL_DB, REDIS_PUBLIC_DB
from workflow_run_repository import record_process_workflow_run

LOSS_REASON = "runtime_state_lost"


def _iso(value):
    return value.isoformat() if isinstance(value, datetime) else value


def _observation_process(document: dict) -> Process:
    """Map the Mongo observation schema to runtime fields at the storage boundary."""
    process_class = {"workflow": WorkflowProcess, "terminal": TerminalProcess}[document["process_type"]]
    return process_class(
        process_id=document["process_id"],
        process_type=document["process_type"],
        status=document["status"],
        parent_process_id=document["parent_process_id"],
        root_process_id=document["root_process_id"],
        terminal_id=document["terminal_id"],
        terminal_process_id=document["terminal_process_id"],
        invocation_id=document["invocation_id"],
        workflow_name=document["workflow_name"],
        start_time=_iso(document["start_time"]),
        finished_at=_iso(document["finished_at"]),
        wait_for=document["wait_for"],
        call_stack=document["call_stack"],
        events=document["events"],
        input=document["input"],
        result=document["output"],
        node_trace=document["nodes"],
        active_duration_ms=document["active_duration_ms"],
        current_node_id=document["current_node_id"],
        error=document.get("error"),
    )


def _start_time(process: Process):
    return datetime.fromisoformat(process.start_time)


def _finalize_lost_process(
    client, process: Process, records: dict[str, Process], recovered: dict[str, Process],
):
    """Replay derived records even if a previous recovery stopped halfway through."""
    if process.process_type == "workflow":
        record_process_workflow_run({
            "run_id": process.invocation_id,
            "process_id": process.process_id,
            "parent_process_id": process.parent_process_id,
            "root_process_id": process.root_process_id,
            "workflow_name": process.workflow_name,
            "call_stack": process.call_stack,
            "started_at": _start_time(process),
            "finished_at": datetime.fromisoformat(process.finished_at),
            "duration_ms": None,
            "active_duration_ms": process.active_duration_ms,
            "status": "lost",
            "input": process.input,
            "output": process.result,
            "node_trace": process.node_trace,
            "error": process.error,
        })

    root = recovered.get(process.root_process_id, process)
    terminal_id = root.terminal_id
    if not terminal_id:
        return
    roots = [p for p in recovered.values() if p.terminal_id == terminal_id and p.is_root]
    if roots:
        root = max(roots, key=_start_time)
    if root.root_process_id in records:
        return
    if any(record.terminal_id == terminal_id and (
            record.is_active
            or (record.is_root and _start_time(record) >= _start_time(root)))
            for record in records.values()):
        return

    session = {
        "terminal_id": terminal_id,
        "status": "closed",
        "start_time": root.start_time,
        "closed_at": root.finished_at,
        "workflow_name": root.workflow_name,
        "workflow_status": "lost",
        "wait_kind": None,
    }
    with client.pipeline(transaction=True) as pipe:
        pipe.hdel(TERMINAL_INDEX, terminal_id)
        pipe.execute_command("SELECT", REDIS_PUBLIC_DB)
        pipe.hset(TERMINAL_SESSIONS, terminal_id, json.dumps(session, ensure_ascii=False))
        pipe.execute_command("SELECT", REDIS_KERNEL_DB)
        pipe.execute()


def reconcile_lost_processes(client, logs):
    """Reconcile missing runtime records against durable process observations."""
    records = {pid: Process.from_record(json.loads(raw))
               for pid, raw in client.hgetall(PROCESSTABLE).items()}
    query = {"$or": [
        {"status": {"$nin": sorted(TERMINAL_STATUSES)}, "finished_at": None},
        {"status": "lost"},
    ]}
    recovered = {}
    for document in logs.find(query):
        process_id = document["process_id"]
        # Recheck the authoritative state before changing durable observations.
        if client.hexists(PROCESSTABLE, process_id):
            continue
        if document["status"] != "lost":
            detected_at = datetime.now(timezone.utc)
            document = logs.find_one_and_update(
                {"_id": document["_id"], "status": document["status"],
                 "observed_at": document["observed_at"], "finished_at": None},
                {"$set": {"status": "lost", "finished_at": detected_at, "wait_for": None},
                 "$push": {"events": {"event": "lost", "status": "lost",
                                       "timestamp": detected_at.isoformat(), "reason": LOSS_REASON}}},
                return_document=ReturnDocument.AFTER,
            )
            if document is None:
                continue
        recovered[process_id] = _observation_process(document)
    for process in recovered.values():
        _finalize_lost_process(client, process, records, recovered)
