import copy
import json
import os
import secrets
from datetime import datetime, timezone
from uuid import uuid4

import redis

from process import Process, WorkflowProcess, TerminalProcess, TERMINAL_STATUSES
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


def _read_process_record(client, process_id: str) -> Process:
    raw = client.hget(PROCESSTABLE, process_id)
    if raw is None:
        raise KeyError(f"process not found: {process_id}")
    process = Process.from_record(json.loads(raw))
    if process.process_id != process_id:
        raise ValueError(f"invalid process data: {process_id}")
    return process


def _encode_process(process: Process) -> str:
    return json.dumps(process.to_record(), ensure_ascii=False, allow_nan=False)


def _wake_record(process: Process) -> None:
    wait_for = process.wait_for
    process.wake(wait_for["process_id"], wait_for["kind"])


def wake_process(client, process_id: str, source_process_id: str, event_kind: str) -> Process:
    """匹配等待事件后，在一个 Redis 事务中唤醒并重新排队进程。"""
    if not isinstance(source_process_id, str) or not source_process_id:
        raise ValueError("source_process_id must be a non-empty string")
    if event_kind not in {"process_exit", "terminal_message"}:
        raise ValueError("unsupported process wake event kind")
    while True:
        with client.pipeline() as pipe:
            try:
                pipe.watch(PROCESSTABLE, TERMINAL_INDEX)
                process = _read_process_record(pipe, process_id)
                if process.status != "blocked" or process.wait_for != {
                    "kind": event_kind, "process_id": source_process_id,
                }:
                    return process
                current_terminal_process_id = pipe.hget(
                    TERMINAL_INDEX, process.terminal_id
                )
                _wake_record(process)
                existing = _read_terminal_scope(pipe, process)
                pipe.multi()
                pipe.hset(PROCESSTABLE, process_id, _encode_process(process))
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


def enqueue_terminal_input(client, terminal_id: str, content: str) -> WorkflowProcess | None:
    """写入当前路由的 mailbox，并原子唤醒等待该 mailbox 的 workflow。"""
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
                assert isinstance(terminal, TerminalProcess)
                if terminal.status in TERMINAL_STATUSES:
                    return None
                owner = _read_process_record(pipe, terminal.parent_process_id)
                if owner.status in TERMINAL_STATUSES:
                    return None
                existing = _read_terminal_scope(pipe, terminal)
                terminal.enqueue_input(content)
                records = {terminal_process_id: terminal}
                if (owner.status == "blocked" and owner.wait_for == {
                        "kind": "terminal_message", "process_id": terminal_process_id}):
                    _wake_record(owner)
                    records[owner.process_id] = owner
                pipe.multi()
                pipe.hset(PROCESSTABLE, mapping={key: _encode_process(value)
                                                for key, value in records.items()})
                if owner.process_id in records:
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
    """Atomically take all pending input from a terminal process."""
    if not isinstance(terminal_process_id, str) or not terminal_process_id.strip():
        raise ValueError("terminal_process_id must be a non-empty string")
    while True:
        with client.pipeline() as pipe:
            try:
                pipe.watch(PROCESSTABLE)
                terminal = _read_process_record(pipe, terminal_process_id)
                assert isinstance(terminal, TerminalProcess)
                contents = terminal.drain_input()
                if not contents:
                    return []
                pipe.multi()
                pipe.hset(PROCESSTABLE, terminal_process_id, _encode_process(terminal))
                pipe.execute()
                return contents
            except redis.WatchError:
                continue


def _index_process(pipe, process: Process) -> None:
    process_id = process.process_id
    pipe.lrem(READY_PROCESSES, 0, process_id)
    if process.status == "blocked":
        pipe.sadd(BLOCKED_PROCESSES, process_id)
    else:
        pipe.srem(BLOCKED_PROCESSES, process_id)
        if process.status == "ready":
            pipe.lpush(READY_PROCESSES, process_id)


def _read_terminal_scope(client, process: Process) -> dict[str, Process]:
    """Read the root and active terminal needed for public session projection."""
    records = {process.process_id: process}
    if not process.terminal_id:
        return records
    active_id = client.hget(TERMINAL_INDEX, process.terminal_id)
    for process_id in (process.root_process_id, active_id):
        if process_id and process_id not in records:
            records[process_id] = _read_process_record(client, process_id)
    if active_id:
        owner_id = records[active_id].parent_process_id
        if owner_id and owner_id not in records:
            records[owner_id] = _read_process_record(client, owner_id)
    return records


def _queue_terminal_handoff(pipe, terminal_id: str, terminal_process_id: str) -> None:
    """Route future terminal input to the selected active terminal process."""
    pipe.hset(TERMINAL_INDEX, terminal_id, terminal_process_id)


def _queue_terminal_close(pipe, root: Process) -> None:
    """Close a root-owned terminal session and remove its input route."""
    pipe.hdel(TERMINAL_INDEX, root.terminal_id)
    pipe.execute_command("SELECT", REDIS_PUBLIC_DB)
    pipe.hset(TERMINAL_SESSIONS, root.terminal_id, json.dumps({
        "terminal_id": root.terminal_id,
        "status": "closed",
        "start_time": root.start_time,
        "closed_at": root.finished_at,
        "workflow_name": root.workflow_name,
        "workflow_status": root.status,
        "wait_kind": None,
    }, ensure_ascii=False, allow_nan=False))
    pipe.execute_command("SELECT", REDIS_KERNEL_DB)


def _queue_public_updates(
    pipe,
    existing: dict[str, Process],
    updates: dict[str, Process],
    route_terminal_process_id=_UNSET,
    current_terminal_process_id=_UNSET,
) -> None:
    """Publish public session summaries and scheduler projections."""
    projected = dict(existing)
    projected.update(updates)

    def lookup(process_id: str | None) -> Process | None:
        return projected.get(process_id) if process_id else None

    roots = {process.root_process_id for process in updates.values()}
    for root_id in roots:
        root = projected[root_id]
        terminal_id = root.terminal_id
        owner = root
        if route_terminal_process_id is _UNSET:
            current = lookup(current_terminal_process_id)
            if current is not None and current.is_active:
                owner = lookup(current.parent_process_id) or root
        elif route_terminal_process_id:
            current = lookup(route_terminal_process_id)
            owner = lookup(current.parent_process_id) or root
        pipe.execute_command("SELECT", REDIS_PUBLIC_DB)
        pipe.hset(TERMINAL_SESSIONS, terminal_id, json.dumps({
            "terminal_id": terminal_id,
            "status": "open",
            "start_time": root.start_time,
            "closed_at": None,
            "workflow_name": owner.workflow_name,
            "workflow_status": owner.status,
            "wait_kind": (owner.wait_for or {}).get("kind"),
        }, ensure_ascii=False, allow_nan=False))
        pipe.execute_command("SELECT", REDIS_KERNEL_DB)

    queue_public_process_updates(pipe, updates)


def publish_process_pair(client, process: Process, terminal: Process) -> None:
    """Publish a complete root workflow and its terminal before making it runnable."""
    with client.pipeline(transaction=True) as pipe:
        pipe.hset(PROCESSTABLE, mapping={
            process.process_id: _encode_process(process),
            terminal.process_id: _encode_process(terminal),
        })
        _queue_public_updates(pipe, {}, {
            process.process_id: process,
            terminal.process_id: terminal,
        }, route_terminal_process_id=terminal.process_id)
        _queue_terminal_handoff(pipe, process.terminal_id, terminal.process_id)
        _index_process(pipe, process)
        pipe.execute()


def claim_process(client, process_id: str) -> tuple[Process, bool]:
    """原子领取 ready workflow，转为 running 并分配本次执行标识。

    领取失败返回当前记录和 False；提交时用 execution_id 拒绝旧执行结果。
    """
    while True:
        with client.pipeline() as pipe:
            try:
                pipe.watch(PROCESSTABLE, TERMINAL_INDEX)
                process = _read_process_record(pipe, process_id)
                if process.status != "ready" or process.is_terminal:
                    return process, False
                current_terminal_process_id = pipe.hget(
                    TERMINAL_INDEX, process.terminal_id
                )
                if process.process_type == "workflow":
                    process.permissions = snapshot_process_permissions(process.permissions)
                    process._workspace_token = process._workspace_token or secrets.token_urlsafe(32)
                process.mark_running(uuid4().hex)
                if not any(item["event"] == "started" for item in process.events):
                    process.record_event("started", dispatch=True)
                else:
                    process.record_event("resumed", dispatch=True)
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


def _commit_execution_transition(
    client, process: Process, child: Process | None = None,
    child_terminal: Process | None = None,
) -> Process:
    """校验执行 fence，并原子提交当前进程及其关联生命周期变化。"""
    process_id = process.process_id
    while True:
        with client.pipeline() as pipe:
            try:
                pipe.watch(PROCESSTABLE, TERMINAL_INDEX)
                current_terminal_process_id = pipe.hget(TERMINAL_INDEX, process.terminal_id)
                saved = _read_process_record(pipe, process_id)
                if saved.status != "running" or saved.execution_id != process.execution_id:
                    return saved

                existing = _read_terminal_scope(pipe, process)
                terminal_id = process.terminal_process_id
                if terminal_id and terminal_id not in existing:
                    existing[terminal_id] = _read_process_record(pipe, terminal_id)
                parent_id = process.parent_process_id
                if parent_id and not process.is_root and parent_id not in existing:
                    existing[parent_id] = _read_process_record(pipe, parent_id)
                if parent_id and not process.is_root:
                    parent_terminal_id = existing[parent_id].terminal_process_id
                    if parent_terminal_id not in existing:
                        existing[parent_terminal_id] = _read_process_record(pipe, parent_terminal_id)

                candidate = copy.deepcopy(process)
                records = {process_id: candidate}
                terminal = existing.get(candidate.terminal_process_id)
                if (candidate.status == "blocked"
                        and candidate.wait_for == {
                            "kind": "terminal_message", "process_id": candidate.terminal_process_id}
                        and terminal is not None and terminal.input_queue):
                    candidate.mark_ready()
                if candidate.status == "ready":
                    candidate.record_event("yielded")
                elif candidate.status == "blocked":
                    candidate.record_event("blocked", wait_for=candidate.wait_for)
                elif candidate.status in TERMINAL_STATUSES:
                    candidate.record_event(candidate.status, error=candidate.error)

                if child is not None:
                    if child.process_id in existing or pipe.hexists(PROCESSTABLE, child.process_id):
                        raise ValueError("child process already exists")
                    records[child.process_id] = child
                    records[child_terminal.process_id] = child_terminal

                if process.status in TERMINAL_STATUSES:
                    if terminal is not None and terminal.parent_process_id == process_id:
                        terminal.finish("completed", finished_at=process.finished_at)
                        terminal.drain_input()
                        records[terminal.process_id] = terminal
                    if parent_id and not process.is_root:
                        parent = existing[parent_id]
                        if parent.status == "blocked" and parent.wait_for == {
                            "kind": "process_exit", "process_id": process_id,
                        }:
                            _wake_record(parent)
                            records[parent_id] = parent

                route_terminal_process_id = _UNSET
                if child_terminal is not None:
                    route_terminal_process_id = child_terminal.process_id
                elif candidate.status in TERMINAL_STATUSES:
                    if candidate.is_root:
                        route_terminal_process_id = None
                    else:
                        parent = existing.get(candidate.parent_process_id)
                        route_terminal_process_id = parent.terminal_process_id if parent else None

                pipe.multi()
                pipe.hset(PROCESSTABLE, mapping={key: _encode_process(value)
                                                for key, value in records.items()})
                for record in records.values():
                    _index_process(pipe, record)
                _queue_public_updates(
                    pipe, existing, records,
                    route_terminal_process_id=route_terminal_process_id,
                    current_terminal_process_id=current_terminal_process_id,
                )
                if child_terminal is not None:
                    _queue_terminal_handoff(pipe, candidate.terminal_id, child_terminal.process_id)
                elif candidate.status in TERMINAL_STATUSES:
                    if candidate.is_root:
                        _queue_terminal_close(pipe, candidate)
                    elif route_terminal_process_id:
                        _queue_terminal_handoff(
                            pipe, candidate.terminal_id, route_terminal_process_id
                        )
                pipe.execute()
                return candidate
            except redis.WatchError:
                continue


def commit_execution_slice(client, process: Process) -> Process:
    """提交无 child spawn 的一次执行片段及其状态/调度副作用。"""
    return _commit_execution_transition(client, process)


def spawn_child_and_suspend_parent(
    client, parent: Process, child: Process, child_terminal: Process,
) -> Process:
    """挂起父进程，并原子创建/排入 child 与交接 terminal 路由。"""
    parent.block({"kind": "process_exit", "process_id": child.process_id})
    return _commit_execution_transition(client, parent, child, child_terminal)


def terminate_process_tree(client, process_id: str) -> list[Process]:
    """原子终止目标及后代，并处理树外等待者和 terminal 路由。"""
    while True:
        with client.pipeline() as pipe:
            try:
                pipe.watch(PROCESSTABLE)
                records = {key: Process.from_record(json.loads(raw))
                           for key, raw in pipe.hgetall(PROCESSTABLE).items()}
                if process_id not in records:
                    raise KeyError(f"process not found: {process_id}")
                selected = {process_id}
                while True:
                    descendants = {key for key, value in records.items()
                                   if value.parent_process_id in selected}
                    if descendants <= selected:
                        break
                    selected.update(descendants)
                now = datetime.now(timezone.utc).isoformat()
                changed = []
                for key in selected:
                    record = records[key]
                    if record.is_active:
                        record.finish("terminated", finished_at=now)
                        if record.is_terminal:
                            record.drain_input()
                        changed.append(record)
                parent_id = records[process_id].parent_process_id
                parent = records.get(parent_id)
                wake_parent = (parent_id not in selected and parent is not None
                               and parent.status == "blocked"
                               and parent.wait_for == {
                                   "kind": "process_exit", "process_id": process_id,
                               })
                if wake_parent:
                    _wake_record(parent)
                updates = changed + ([parent] if wake_parent else [])
                route_terminal_process_id = _UNSET
                target = records[process_id]
                if target.process_type == "workflow":
                    parent_id = target.parent_process_id
                    parent = records.get(parent_id) if parent_id else None
                    route_terminal_process_id = (
                        parent.terminal_process_id
                        if parent is not None and parent_id not in selected
                        else None
                    )
                pipe.multi()
                if updates:
                    pipe.hset(PROCESSTABLE, mapping={item.process_id: _encode_process(item)
                                                    for item in updates})
                    for record in updates:
                        _index_process(pipe, record)
                    _queue_public_updates(
                        pipe,
                        records,
                        {item.process_id: item for item in updates},
                        route_terminal_process_id=route_terminal_process_id,
                    )
                    if target.process_type == "workflow":
                        if target.is_root:
                            if target in changed:
                                _queue_terminal_close(pipe, target)
                        elif route_terminal_process_id:
                            _queue_terminal_handoff(
                                pipe, target.terminal_id, route_terminal_process_id
                            )
                pipe.execute()
                return changed
            except redis.WatchError:
                continue


def kill_process_tree(client, process_id: str) -> list[Process]:
    """从目标定位 root，原子 kill 整棵 workflow 树并关闭 root 会话。"""
    while True:
        with client.pipeline() as pipe:
            try:
                pipe.watch(PROCESSTABLE, TERMINAL_INDEX)
                records = {key: Process.from_record(json.loads(raw))
                           for key, raw in pipe.hgetall(PROCESSTABLE).items()}
                target = records.get(process_id)
                if target is None:
                    raise KeyError(f"process not found: {process_id}")
                root_id = target.root_process_id or process_id
                root = records[root_id]
                assert root.process_type == "workflow"

                children_by_parent = {}
                for child_id, child in records.items():
                    parent_id = child.parent_process_id
                    if parent_id:
                        children_by_parent.setdefault(parent_id, []).append(child_id)
                ordered = []
                stack = [(root_id, False)]
                visited = set()
                while stack:
                    current_id, expanded = stack.pop()
                    if expanded:
                        ordered.append(current_id)
                        continue
                    if current_id in visited:
                        continue
                    visited.add(current_id)
                    stack.append((current_id, True))
                    children = sorted(children_by_parent.get(current_id, []))
                    stack.extend((child_id, False) for child_id in reversed(children))

                now = datetime.now(timezone.utc).isoformat()
                changed = []
                for current_id in ordered:
                    record = records[current_id]
                    if record.is_active:
                        record.finish("killed", finished_at=now)
                        if record.is_terminal:
                            record.drain_input()
                        changed.append(record)

                pipe.multi()
                if changed:
                    pipe.hset(PROCESSTABLE, mapping={item.process_id: _encode_process(item)
                                                     for item in changed})
                    for record in changed:
                        _index_process(pipe, record)
                    _queue_public_updates(
                        pipe, records, {item.process_id: item for item in changed},
                        route_terminal_process_id=None,
                    )
                    if root.is_root:
                        _queue_terminal_close(pipe, root)
                pipe.execute()
                return changed
            except redis.WatchError:
                continue
