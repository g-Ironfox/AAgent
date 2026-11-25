"""Process data models and lifecycle-independent operations."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

TERMINAL_STATUSES = frozenset({"completed", "failed", "terminated", "killed", "lost"})


@dataclass
class Process:
    process_id: str
    process_type: str
    status: str
    terminal_id: str | None = None
    terminal_process_id: str | None = None
    parent_process_id: str | None = None
    root_process_id: str | None = None
    start_time: str | None = None
    finished_at: str | None = None
    wait_for: dict | None = None
    events: list[dict] = field(default_factory=list)
    invocation_id: str | None = None
    ancestor_invocation_ids: list[str] = field(default_factory=list)
    context_ids: list[str] = field(default_factory=list)
    active_duration_ms: float = 0
    node_trace: list[dict] = field(default_factory=list)
    pending_call: dict | None = None
    workflow_name: str | None = None
    workflow_file: str | None = None
    workflow_file_id: str | None = None
    workflow: str | None = None
    current_node_id: int | None = None
    control_port: str | None = None
    input: dict = field(default_factory=dict)
    result: dict = field(default_factory=dict)
    error: str | None = None
    permissions: dict = field(default_factory=dict)
    _workspace_token: str | None = None
    execution_timeout_ms: int | None = None
    execution_id: str | None = None
    call_stack: list[str] = field(default_factory=list)
    function_stack: list[dict] = field(default_factory=list)
    function_template: list[dict] | None = None
    active_function_id: str | None = None
    active_function_name: str | None = None
    active_function_call_id: str | None = None
    input_queue: list[str] = field(default_factory=list)

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> Process:
        """在持久化边界将 JSON 字段映射为具体进程类型。"""
        process_class = {"workflow": WorkflowProcess, "terminal": TerminalProcess}[record["process_type"]]
        return process_class(**record)

    def to_record(self) -> dict[str, Any]:
        """在持久化边界把进程对象转换为 JSON 可编码字段。"""
        return asdict(self)

    @property
    def is_root(self) -> bool:
        return self.process_type == "workflow" and self.process_id == self.root_process_id

    @property
    def is_terminal(self) -> bool:
        return self.process_type == "terminal"

    @property
    def is_active(self) -> bool:
        return self.status not in TERMINAL_STATUSES

    def record_event(self, event: str, **details: Any) -> None:
        """把单进程状态变化追加到其本地生命周期历史。"""
        self.events.append({
            "event": event,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": self.status,
            **deepcopy(details),
        })

    def mark_ready(self, *, event: str | None = None, **details: Any) -> None:
        """将当前进程设为可调度状态；不负责入 ready 队列。"""
        self.status = "ready"
        self.wait_for = None
        if event:
            self.record_event(event, **details)

    def mark_running(self, execution_id: str) -> None:
        """记录当前执行尝试的 fence；claim 与队列更新由生命周期层提交。"""
        if self.is_terminal:
            raise ValueError("terminal processes are passive and cannot be claimed")
        if self.status != "ready":
            raise ValueError("only a ready process can be claimed")
        self.status = "running"
        self.execution_id = execution_id

    def block(self, wait_for: dict, *, event: str | None = None) -> None:
        """记录当前进程的等待条件，不创建被等待的进程。"""
        self.status = "blocked"
        self.wait_for = deepcopy(wait_for)
        if event:
            self.record_event(event, wait_for=wait_for)

    def wake(self, source_process_id: str, event_kind: str) -> bool:
        """等待源和事件匹配时唤醒当前进程；调度入队由生命周期层完成。"""
        if self.status != "blocked" or self.wait_for != {
            "kind": event_kind, "process_id": source_process_id,
        }:
            return False
        previous_wait = deepcopy(self.wait_for)
        self.mark_ready()
        self.record_event("woken", wait_for=previous_wait)
        return True

    def finish(self, status: str, *, finished_at: str | None = None,
               error: str | None = None, record_event: bool = True) -> None:
        """结束当前进程记录；是否结束根会话由生命周期调用方决定。"""
        self.status = status
        self.wait_for = None
        self.finished_at = finished_at or datetime.now(timezone.utc).isoformat()
        if error is not None:
            self.error = error
        if record_event:
            self.record_event(status, error=error)


@dataclass
class WorkflowProcess(Process):
    pass


@dataclass
class TerminalProcess(Process):

    def enqueue_input(self, content: str) -> None:
        self.input_queue.append(content)

    def drain_input(self) -> list[str]:
        contents = self.input_queue
        self.input_queue = []
        return contents
