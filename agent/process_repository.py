import copy
import json
import os
import secrets
from datetime import datetime, timezone
from uuid import uuid4

import redis

from process_permissions import snapshot_process_permissions
from redis_client import REDIS_KERNEL_DB, REDIS_PUBLIC_DB
from scheduler_projection import queue_public_process_updates

PROCESSTABLE = os.getenv("ProcessTable", "processtable")
READY_PROCESSES = os.getenv("ReadyProcesses", "ready_processes")
BLOCKED_PROCESSES = os.getenv("BlockedProcesses", "blocked_processes")
EXTERNAL_EVENTS = os.getenv("ExternalEvents", "external_events")
TERMINAL_INDEX = os.getenv("TerminalIndex", "terminal_index")
TERMINAL_SESSIONS = os.getenv("TerminalSessions", "terminal_sessions")
_UNSET = object()


def _read_process_record(client, process_id: str) -> dict:
    raw = client.hget(PROCESSTABLE, process_id)
    if raw is None:
        raise KeyError(f"process not found: {process_id}")
    process = json.loads(raw)
    if not isinstance(process, dict) or process.get("process_id") != process_id:
        raise ValueError(f"invalid process data: {process_id}")
    return process


def record_process_event(process: dict, event: str, **details) -> None:
    """Keep lifecycle history in the same Redis record as its committed state."""
    process.setdefault("events", []).append({
        "event": event,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": process["status"],
        **copy.deepcopy(details),
    })


def _wake_record(process: dict) -> None:
    wait_for = process.get("wait_for")
    process.update(status="ready", wait_for=None)
    record_process_event(process, "woken", wait_for=wait_for)


def wake_process(client, process_id: str, source_process_id: str, event_kind: str) -> dict:
    """Atomically wake only the matching blocked process and enqueue it once."""
    if not isinstance(source_process_id, str) or not source_process_id:
        raise ValueError("source_process_id must be a non-empty string")
    if event_kind not in {"process_exit", "terminal_message"}:
        raise ValueError("unsupported process wake event kind")
    while True:
        with client.pipeline() as pipe:
            try:
                pipe.watch(PROCESSTABLE, TERMINAL_INDEX)
                process = _read_process_record(pipe, process_id)
                if (
                    process.get("status") != "blocked"
                    or process.get("wait_for")
                    != {"kind": event_kind, "process_id": source_process_id}
                ):
                    return process
                current_terminal_process_id = pipe.hget(
                    TERMINAL_INDEX, process.get("terminal_id")
                )
                _wake_record(process)
                existing = _read_terminal_scope(pipe, process)
                pipe.multi()
                pipe.hset(PROCESSTABLE, process_id, json.dumps(process, ensure_ascii=False, allow_nan=False))
                pipe.srem(BLOCKED_PROCESSES, process_id)
                pipe.lrem(READY_PROCESSES, 0, process_id)
                pipe.lpush(READY_PROCESSES, process_id)
                _queue_public_updates(
                    pipe,
                    existing,
                    {process_id: process},
                    current_terminal_process_id=current_terminal_process_id,
                )
                pipe.execute()
                return process
            except redis.WatchError:
                continue


def enqueue_terminal_input(client, terminal_id: str, content: str) -> dict | None:
    """Buffer input and wake its waiting owner in the same Redis transaction."""
    if not isinstance(terminal_id, str) or not terminal_id.strip():
        raise ValueError("terminal_id must be a non-empty string")
    if not isinstance(content, str) or not content.strip():
        raise ValueError("terminal message content must be non-empty text")
    while True:
        with client.pipeline() as pipe:
            try:
                pipe.watch(PROCESSTABLE, TERMINAL_INDEX)
                terminal_process_id = pipe.hget(TERMINAL_INDEX, terminal_id)
                if not terminal_process_id:
                    return None
                terminal = _read_process_record(pipe, terminal_process_id)
                if (terminal.get("process_type") != "terminal"
                        or terminal.get("terminal_id") != terminal_id
                        or terminal.get("status") in TERMINAL_STATUSES):
                    return None
                owner = _read_process_record(pipe, terminal["parent_process_id"])
                if owner.get("status") in TERMINAL_STATUSES:
                    return None
                existing = _read_terminal_scope(pipe, terminal)
                terminal.setdefault("input_queue", []).append(content)
                records = {terminal_process_id: terminal}
                if (owner.get("status") == "blocked" and owner.get("wait_for") == {
                        "kind": "terminal_message", "process_id": terminal_process_id}):
                    _wake_record(owner)
                    records[owner["process_id"]] = owner
                pipe.multi()
                pipe.hset(PROCESSTABLE, mapping={key: _encode_process(value)
                                                for key, value in records.items()})
                if owner["process_id"] in records:
                    _index_process(pipe, owner)
                _queue_public_updates(
                    pipe,
                    existing,
                    records,
                    current_terminal_process_id=terminal_process_id,
                )
                pipe.execute()
                return owner
            except redis.WatchError:
                continue


def read_terminal_input_queue(client, terminal_process_id: str) -> list[str]:
    """Snapshot pending input; commit_process acknowledges it with node progress."""
    if not isinstance(terminal_process_id, str) or not terminal_process_id.strip():
        raise ValueError("terminal_process_id must be a non-empty string")
    terminal = _read_process_record(client, terminal_process_id)
    if terminal.get("process_type") != "terminal":
        raise ValueError("terminal process required")
    return list(terminal.get("input_queue", []))


TERMINAL_STATUSES = {"completed", "failed", "terminated", "lost"}


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


def _queue_public_updates(
    pipe,
    existing: dict[str, dict],
    updates: dict[str, dict],
    route_terminal_process_id=_UNSET,
    current_terminal_process_id=_UNSET,
) -> None:
    """Publish routing, public sessions, and projections in one transaction.

    Route changes are supplied by the lifecycle transition that caused them;
    routine process updates only preserve the already indexed terminal.
    """
    projected = dict(existing)
    projected.update(updates)

    def lookup(process_id: str | None) -> dict | None:
        if not process_id:
            return None
        process = projected.get(process_id)
        if process is not None:
            return process
        raw = pipe.hget(PROCESSTABLE, process_id)
        return json.loads(raw) if raw is not None else None

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
        owner = root
        if closed or route_terminal_process_id is None:
            pipe.hdel(TERMINAL_INDEX, terminal_id)
        elif route_terminal_process_id is _UNSET:
            current = lookup(current_terminal_process_id)
            if current is not None and current.get("status") not in TERMINAL_STATUSES:
                owner = lookup(current.get("parent_process_id")) or root
        else:
            current = lookup(route_terminal_process_id)
            if current is None or current.get("process_type") != "terminal":
                raise ValueError("terminal route target is missing or invalid")
            if current.get("terminal_id") != terminal_id:
                raise ValueError("terminal route target belongs to another terminal")
            if current.get("status") in TERMINAL_STATUSES:
                raise ValueError("terminal route target is not active")
            pipe.hset(TERMINAL_INDEX, terminal_id, route_terminal_process_id)
            owner = lookup(current.get("parent_process_id")) or root
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

    queue_public_process_updates(pipe, updates)


def publish_process_pair(client, process: dict, terminal: dict) -> None:
    """Publish a complete root workflow and its terminal before making it runnable."""
    with client.pipeline(transaction=True) as pipe:
        pipe.hset(PROCESSTABLE, mapping={
            process["process_id"]: _encode_process(process),
            terminal["process_id"]: _encode_process(terminal),
        })
        _queue_public_updates(pipe, {}, {
            process["process_id"]: process,
            terminal["process_id"]: terminal,
        }, route_terminal_process_id=terminal["process_id"])
        _index_process(pipe, process)
        pipe.execute()


def claim_process(client, process_id: str) -> tuple[dict, bool]:
    """Ignore stale queue entries and prevent simultaneous execution of one process."""
    while True:
        with client.pipeline() as pipe:
            try:
                pipe.watch(PROCESSTABLE, TERMINAL_INDEX)
                process = _read_process_record(pipe, process_id)
                if process.get("status") != "ready" or process.get("process_type") == "terminal":
                    return process, False
                current_terminal_process_id = pipe.hget(
                    TERMINAL_INDEX, process.get("terminal_id")
                )
                if process.get("process_type") == "workflow":
                    process["permissions"] = snapshot_process_permissions(process.get("permissions"))
                    process.setdefault("_workspace_token", secrets.token_urlsafe(32))
                process["status"] = "running"
                process["execution_id"] = uuid4().hex
                if not any(item["event"] == "started" for item in process.get("events", [])):
                    record_process_event(process, "started", dispatch=True)
                else:
                    record_process_event(process, "resumed", dispatch=True)
                existing = _read_terminal_scope(pipe, process)
                pipe.multi()
                pipe.hset(PROCESSTABLE, process_id, _encode_process(process))
                pipe.lrem(READY_PROCESSES, 0, process_id)
                pipe.srem(BLOCKED_PROCESSES, process_id)
                _queue_public_updates(
                    pipe,
                    existing,
                    {process_id: process},
                    current_terminal_process_id=current_terminal_process_id,
                )
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
                pipe.watch(PROCESSTABLE, TERMINAL_INDEX)
                existing = {
                    key: json.loads(raw)
                    for key, raw in pipe.hgetall(PROCESSTABLE).items()
                }
                current_terminal_process_id = pipe.hget(
                    TERMINAL_INDEX, process.get("terminal_id")
                )
                saved = _read_process_record(pipe, process_id)
                if (saved.get("status") != "running"
                        or saved.get("execution_id") != process.get("execution_id")):
                    return saved
                candidate = copy.deepcopy(process)
                batch = candidate.pop("_terminal_input_batch", None)
                records = {process_id: candidate}
                terminal_process_id = candidate.get("terminal_process_id")
                terminal = existing.get(terminal_process_id)
                if batch and candidate.get("status") == "ready":
                    if terminal is None or terminal.get("parent_process_id") != process_id:
                        raise ValueError("terminal input owner mismatch")
                    queue = terminal.get("input_queue", [])
                    if queue[:len(batch)] != batch:
                        raise ValueError("terminal input queue changed before commit")
                    terminal["input_queue"] = queue[len(batch):]
                    records[terminal_process_id] = terminal
                if (candidate.get("status") == "blocked"
                        and candidate.get("wait_for") == {
                            "kind": "terminal_message", "process_id": terminal_process_id}
                        and terminal is not None and terminal.get("input_queue")):
                    # Input may have arrived after the node observed an empty queue.
                    candidate.update(status="ready", wait_for=None)
                if candidate.get("status") == "ready":
                    record_process_event(candidate, "yielded")
                elif candidate.get("status") == "blocked":
                    record_process_event(candidate, "blocked", wait_for=candidate.get("wait_for"))
                elif candidate.get("status") in TERMINAL_STATUSES:
                    record_process_event(candidate, candidate["status"], error=candidate.get("error"))
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
                            terminal.update(status="terminated", wait_for=None, input_queue=[],
                                            finished_at=process["finished_at"])
                            record_process_event(terminal, "terminated")
                            records[terminal_process_id] = terminal
                    parent_id = process.get("parent_process_id")
                    raw_parent = pipe.hget(PROCESSTABLE, parent_id) if parent_id else None
                    if raw_parent is not None:
                        parent = json.loads(raw_parent)
                        if (parent.get("status") == "blocked"
                                and parent.get("wait_for") == {
                                    "kind": "process_exit", "process_id": process_id,
                                }):
                            _wake_record(parent)
                            records[parent_id] = parent
                route_terminal_process_id = _UNSET
                if child_terminal is not None:
                    route_terminal_process_id = child_terminal["process_id"]
                elif candidate.get("status") in TERMINAL_STATUSES:
                    parent_id = candidate.get("parent_process_id")
                    parent = existing.get(parent_id) if parent_id else None
                    route_terminal_process_id = (
                        parent.get("terminal_process_id") if parent is not None else None
                    )
                pipe.multi()
                pipe.hset(PROCESSTABLE, mapping={key: _encode_process(value)
                                                for key, value in records.items()})
                for record in records.values():
                    _index_process(pipe, record)
                _queue_public_updates(
                    pipe,
                    existing,
                    records,
                    route_terminal_process_id=route_terminal_process_id,
                    current_terminal_process_id=current_terminal_process_id,
                )
                pipe.execute()
                return candidate
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
                        if record.get("process_type") == "terminal":
                            record["input_queue"] = []
                        record_process_event(record, "terminated")
                        changed.append(record)
                parent_id = records[process_id].get("parent_process_id")
                parent = records.get(parent_id)
                wake_parent = (parent_id not in selected and parent is not None
                               and parent.get("status") == "blocked"
                               and parent.get("wait_for") == {
                                   "kind": "process_exit", "process_id": process_id,
                               })
                if wake_parent:
                    _wake_record(parent)
                updates = changed + ([parent] if wake_parent else [])
                route_terminal_process_id = _UNSET
                target = records[process_id]
                if target.get("process_type") == "workflow":
                    parent_id = target.get("parent_process_id")
                    parent = records.get(parent_id) if parent_id else None
                    route_terminal_process_id = (
                        parent.get("terminal_process_id")
                        if parent is not None and parent_id not in selected
                        else None
                    )
                pipe.multi()
                if updates:
                    pipe.hset(PROCESSTABLE, mapping={item["process_id"]: _encode_process(item)
                                                    for item in updates})
                    for record in updates:
                        _index_process(pipe, record)
                    _queue_public_updates(
                        pipe,
                        records,
                        {item["process_id"]: item for item in updates},
                        route_terminal_process_id=route_terminal_process_id,
                    )
                pipe.execute()
                return changed
            except redis.WatchError:
                continue
