import json
import os
from datetime import datetime, timezone
from uuid import uuid4

import redis

from redis_client import REDIS_KERNEL_DB, REDIS_PUBLIC_DB

PROCESSTABLE = os.getenv("ProcessTable", "processtable")
READY_PROCESSES = os.getenv("ReadyProcesses", "ready_processes")
BLOCKED_PROCESSES = os.getenv("BlockedProcesses", "blocked_processes")
EXTERNAL_EVENTS = os.getenv("ExternalEvents", "external_events")
TERMINAL_INDEX = os.getenv("TerminalIndex", "terminal_index")
TERMINAL_SESSIONS = os.getenv("TerminalSessions", "terminal_sessions")


def _read_process_record(client, process_id: str) -> dict:
    raw = client.hget(PROCESSTABLE, process_id)
    if raw is None:
        raise KeyError(f"process not found: {process_id}")
    process = json.loads(raw)
    if not isinstance(process, dict) or process.get("process_id") != process_id:
        raise ValueError(f"invalid process data: {process_id}")
    return process


def wake_process(client, process_id: str, source_process_id: str, event_kind: str) -> dict:
    """Atomically wake only the matching blocked process and enqueue it once."""
    if not isinstance(source_process_id, str) or not source_process_id:
        raise ValueError("source_process_id must be a non-empty string")
    if event_kind not in {"process_exit", "terminal_message"}:
        raise ValueError("unsupported process wake event kind")
    while True:
        with client.pipeline() as pipe:
            try:
                pipe.watch(PROCESSTABLE)
                process = _read_process_record(pipe, process_id)
                if (
                    process.get("status") != "blocked"
                    or process.get("wait_for")
                    != {"kind": event_kind, "process_id": source_process_id}
                ):
                    return process
                process["status"] = "ready"
                process["wait_for"] = None
                existing = _read_terminal_scope(pipe, process)
                pipe.multi()
                pipe.hset(PROCESSTABLE, process_id, json.dumps(process, ensure_ascii=False, allow_nan=False))
                pipe.srem(BLOCKED_PROCESSES, process_id)
                pipe.lrem(READY_PROCESSES, 0, process_id)
                pipe.lpush(READY_PROCESSES, process_id)
                _queue_terminal_updates(pipe, existing, {process_id: process})
                pipe.execute()
                return process
            except redis.WatchError:
                continue


TERMINAL_STATUSES = {"completed", "failed", "terminated"}


def _encode_process(process: dict) -> str:
    return json.dumps(process, ensure_ascii=False, allow_nan=False)


def _index_process(pipe, process: dict) -> None:
    process_id = process["process_id"]
    pipe.lrem(READY_PROCESSES, 0, process_id)
    if process.get("status") == "blocked":
        pipe.sadd(BLOCKED_PROCESSES, process_id)
    else:
        pipe.srem(BLOCKED_PROCESSES, process_id)
        if process.get("status") == "ready":
            pipe.lpush(READY_PROCESSES, process_id)


def _read_terminal_scope(client, process: dict) -> dict[str, dict]:
    """Read only the root and active terminal needed for a public activity update."""
    records = {process["process_id"]: process}
    terminal_id = process.get("terminal_id")
    if not terminal_id:
        return records
    active_id = client.hget(TERMINAL_INDEX, terminal_id)
    for process_id in (process.get("root_process_id"), active_id):
        if process_id and process_id not in records:
            records[process_id] = _read_process_record(client, process_id)
    if active_id:
        owner_id = records[active_id].get("parent_process_id")
        if owner_id and owner_id not in records:
            records[owner_id] = _read_process_record(client, owner_id)
    return records


def _queue_terminal_updates(
    pipe,
    existing: dict[str, dict],
    updates: dict[str, dict],
) -> None:
    """Publish routing and public session state in the process transaction."""
    projected = dict(existing)
    projected.update(updates)
    terminal_ids = {
        process.get("terminal_id")
        for process in updates.values()
        if isinstance(process, dict) and process.get("process_type") in {"terminal", "workflow"}
    }
    for terminal_id in terminal_ids:
        if not isinstance(terminal_id, str) or not terminal_id:
            continue
        root = next((
            process for process in projected.values()
            if process.get("process_type") == "workflow"
            and process.get("terminal_id") == terminal_id
            and process.get("root_process_id") == process.get("process_id")
        ), None)
        if root is None:
            continue
        closed = root.get("status") in TERMINAL_STATUSES
        candidates = [
            process for process in projected.values()
            if process.get("process_type") == "terminal"
            and process.get("terminal_id") == terminal_id
            and process.get("status") not in TERMINAL_STATUSES
        ]
        owner = root
        if candidates and not closed:
            current = max(candidates, key=lambda process: process.get("start_time") or "")
            pipe.hset(TERMINAL_INDEX, terminal_id, current["process_id"])
            owner = projected.get(current.get("parent_process_id"), root)
        else:
            pipe.hdel(TERMINAL_INDEX, terminal_id)
        # SELECT is queued inside MULTI/EXEC; restore the pooled connection
        # before EXEC finishes, including when another command returns an error.
        pipe.execute_command("SELECT", REDIS_PUBLIC_DB)
        pipe.hset(TERMINAL_SESSIONS, terminal_id, _encode_process({
            "terminal_id": terminal_id,
            "status": "closed" if closed else "open",
            "start_time": root["start_time"],
            "closed_at": root.get("finished_at") if closed else None,
            "workflow_name": owner.get("workflow_name"),
            "workflow_status": owner.get("status"),
            "wait_kind": (owner.get("wait_for") or {}).get("kind"),
        }))
        pipe.execute_command("SELECT", REDIS_KERNEL_DB)


def publish_process_pair(client, process: dict, terminal: dict) -> None:
    """Publish a complete root workflow and its terminal before making it runnable."""
    with client.pipeline(transaction=True) as pipe:
        pipe.hset(PROCESSTABLE, mapping={
            process["process_id"]: _encode_process(process),
            terminal["process_id"]: _encode_process(terminal),
        })
        _queue_terminal_updates(pipe, {}, {
            process["process_id"]: process,
            terminal["process_id"]: terminal,
        })
        _index_process(pipe, process)
        pipe.execute()


def claim_process(client, process_id: str) -> tuple[dict, bool]:
    """Ignore stale queue entries and prevent simultaneous execution of one process."""
    while True:
        with client.pipeline() as pipe:
            try:
                pipe.watch(PROCESSTABLE)
                process = _read_process_record(pipe, process_id)
                if process.get("status") != "ready" or process.get("process_type") == "terminal":
                    return process, False
                process["status"] = "running"
                process["execution_id"] = uuid4().hex
                existing = _read_terminal_scope(pipe, process)
                pipe.multi()
                pipe.hset(PROCESSTABLE, process_id, _encode_process(process))
                pipe.lrem(READY_PROCESSES, 0, process_id)
                pipe.srem(BLOCKED_PROCESSES, process_id)
                _queue_terminal_updates(pipe, existing, {process_id: process})
                pipe.execute()
                return process, True
            except redis.WatchError:
                continue


def commit_process(client, process: dict, child: dict | None = None,
                   child_terminal: dict | None = None) -> dict:
    """Commit a step and its spawn/exit effects together, fencing cancelled workers."""
    process_id = process["process_id"]
    while True:
        with client.pipeline() as pipe:
            try:
                pipe.watch(PROCESSTABLE)
                existing = {
                    key: json.loads(raw)
                    for key, raw in pipe.hgetall(PROCESSTABLE).items()
                }
                saved = _read_process_record(pipe, process_id)
                if (saved.get("status") != "running"
                        or saved.get("execution_id") != process.get("execution_id")):
                    return saved
                records = {process_id: process}
                if child is not None:
                    if child_terminal is None:
                        raise ValueError("child terminal is required")
                    if pipe.hexists(PROCESSTABLE, child["process_id"]):
                        raise ValueError("child process already exists")
                    records[child["process_id"]] = child
                    records[child_terminal["process_id"]] = child_terminal
                if process.get("status") in TERMINAL_STATUSES:
                    terminal_process_id = process.get("terminal_process_id")
                    raw_terminal = pipe.hget(PROCESSTABLE, terminal_process_id) if terminal_process_id else None
                    if raw_terminal is not None:
                        terminal = json.loads(raw_terminal)
                        if (terminal.get("process_type") == "terminal"
                                and terminal.get("parent_process_id") == process_id):
                            terminal.update(status="terminated", wait_for=None,
                                            finished_at=process["finished_at"])
                            records[terminal_process_id] = terminal
                    parent_id = process.get("parent_process_id")
                    raw_parent = pipe.hget(PROCESSTABLE, parent_id) if parent_id else None
                    if raw_parent is not None:
                        parent = json.loads(raw_parent)
                        if (parent.get("status") == "blocked"
                                and parent.get("wait_for") == {
                                    "kind": "process_exit", "process_id": process_id,
                                }):
                            parent.update(status="ready", wait_for=None)
                            records[parent_id] = parent
                pipe.multi()
                pipe.hset(PROCESSTABLE, mapping={key: _encode_process(value)
                                                for key, value in records.items()})
                for record in records.values():
                    _index_process(pipe, record)
                _queue_terminal_updates(pipe, existing, records)
                pipe.execute()
                return process
            except redis.WatchError:
                continue


def terminate_process_tree(client, process_id: str) -> list[dict]:
    """Cancel a workflow and live descendants atomically; wake an external caller."""
    while True:
        with client.pipeline() as pipe:
            try:
                pipe.watch(PROCESSTABLE)
                records = {key: json.loads(raw) for key, raw in pipe.hgetall(PROCESSTABLE).items()}
                if process_id not in records:
                    raise KeyError(f"process not found: {process_id}")
                selected = {process_id}
                while True:
                    descendants = {key for key, value in records.items()
                                   if value.get("parent_process_id") in selected}
                    if descendants <= selected:
                        break
                    selected.update(descendants)
                now = datetime.now(timezone.utc).isoformat()
                changed = []
                for key in selected:
                    record = records[key]
                    if record.get("status") not in TERMINAL_STATUSES:
                        record.update(status="terminated", wait_for=None, finished_at=now)
                        changed.append(record)
                parent_id = records[process_id].get("parent_process_id")
                parent = records.get(parent_id)
                wake_parent = (parent_id not in selected and parent is not None
                               and parent.get("status") == "blocked"
                               and parent.get("wait_for") == {
                                   "kind": "process_exit", "process_id": process_id,
                               })
                if wake_parent:
                    parent.update(status="ready", wait_for=None)
                updates = changed + ([parent] if wake_parent else [])
                pipe.multi()
                if updates:
                    pipe.hset(PROCESSTABLE, mapping={item["process_id"]: _encode_process(item)
                                                    for item in updates})
                    for record in updates:
                        _index_process(pipe, record)
                    _queue_terminal_updates(
                        pipe,
                        records,
                        {item["process_id"]: item for item in updates},
                    )
                pipe.execute()
                return changed
            except redis.WatchError:
                continue
