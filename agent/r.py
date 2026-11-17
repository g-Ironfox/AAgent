import json
import os
from datetime import datetime, timezone
from uuid import uuid4

import redis

REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_SOCKET_TIMEOUT = float(os.getenv("REDIS_SOCKET_TIMEOUT", "30"))

PROCESSTABLE = os.getenv("ProcessTable", "processtable")
READY_PROCESSES = os.getenv("ReadyProcesses", "ready_processes")
BLOCKED_PROCESSES = os.getenv("BlockedProcesses", "blocked_processes")

def get_connection():
    return redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        decode_responses=True,
        socket_timeout=REDIS_SOCKET_TIMEOUT,
    )

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
                pipe.multi()
                pipe.hset(PROCESSTABLE, process_id, json.dumps(process, ensure_ascii=False, allow_nan=False))
                pipe.srem(BLOCKED_PROCESSES, process_id)
                pipe.lrem(READY_PROCESSES, 0, process_id)
                pipe.lpush(READY_PROCESSES, process_id)
                pipe.execute()
                return process
            except redis.WatchError:
                continue


def push_to_queue(queue_name: str, message: dict) -> bool:
    """Push JSON to the left; pop_from_queue reads FIFO from the right."""
    payload = json.dumps(message, ensure_ascii=False, allow_nan=False)
    client = get_connection()
    client.lpush(queue_name, payload)
    return True


def pop_from_queue(queue_name: str, timeout: int = 5):
    client = get_connection()
    item = client.brpop(queue_name, timeout=timeout)
    if item is None:
        return None
    _, payload = item
    return json.loads(payload)


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


def publish_process_pair(client, process: dict, terminal: dict) -> None:
    """Publish a complete root workflow and its terminal before making it runnable."""
    with client.pipeline(transaction=True) as pipe:
        pipe.hset(PROCESSTABLE, mapping={
            process["process_id"]: _encode_process(process),
            terminal["process_id"]: _encode_process(terminal),
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
                pipe.multi()
                pipe.hset(PROCESSTABLE, process_id, _encode_process(process))
                pipe.lrem(READY_PROCESSES, 0, process_id)
                pipe.srem(BLOCKED_PROCESSES, process_id)
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
                    terminal_id = process.get("terminal_process_id")
                    raw_terminal = pipe.hget(PROCESSTABLE, terminal_id) if terminal_id else None
                    if raw_terminal is not None:
                        terminal = json.loads(raw_terminal)
                        if (terminal.get("process_type") == "terminal"
                                and terminal.get("parent_process_id") == process_id):
                            terminal.update(status="terminated", wait_for=None,
                                            finished_at=process["finished_at"])
                            records[terminal_id] = terminal
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
                pipe.execute()
                return changed
            except redis.WatchError:
                continue
