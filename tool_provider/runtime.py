import importlib
import inspect
import json
import logging
import queue
import threading
import time
from typing import Any

from jsonschema import Draft202012Validator
from websocket import WebSocket, WebSocketConnectionClosedException, WebSocketTimeoutException, create_connection

from tool import Tool, ToolContext


logger = logging.getLogger("aagent.tool_provider")


class ToolProvider:
    def __init__(
        self,
        tools: list[Tool],
        server_url: str = "ws://tool_server:8083/ws/providers",
        provider_id: str = "provider-default-01",
        revision: int = 1,
        consumers: int = 1,
        queue_size: int = 128,
        heartbeat_seconds: float = 20,
    ):
        self.server_url = server_url
        self.provider_id = provider_id
        self.revision = revision
        self.tools = {tool.name: tool for tool in tools}
        self.heartbeat_seconds = heartbeat_seconds
        self.tasks: queue.Queue[dict[str, Any] | None] = queue.Queue(maxsize=queue_size)
        self.events: queue.Queue[dict[str, Any]] = queue.Queue()
        self.cancellations: dict[str, threading.Event] = {}
        self.consumer_count = max(1, consumers)
        self._state_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._websocket: WebSocket | None = None
        self._validate_tools()

    @staticmethod
    def discover(module_names: list[str]) -> list[Tool]:
        discovered: dict[str, Tool] = {}
        for module_name in module_names:
            module = importlib.import_module(module_name)
            for _, tool_class in inspect.getmembers(module, inspect.isclass):
                if tool_class is Tool or not issubclass(tool_class, Tool) or inspect.isabstract(tool_class):
                    continue
                tool = tool_class()
                if tool.name in discovered:
                    raise ValueError(f"duplicate tool name: {tool.name}")
                discovered[tool.name] = tool
        if not discovered:
            raise ValueError("no Tool subclasses discovered")
        return list(discovered.values())

    def _validate_tools(self) -> None:
        if len(self.tools) == 0:
            raise ValueError("at least one tool is required")
        for tool in self.tools.values():
            if "." not in tool.name:
                raise ValueError(f"tool name must contain a domain: {tool.name}")
            Draft202012Validator.check_schema(tool.input_schema)
            Draft202012Validator.check_schema(tool.output_schema)

    def start(self, daemon: bool = True) -> threading.Thread:
        if self._thread and self._thread.is_alive():
            return self._thread
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self.run,
            name=f"tool-provider-{self.provider_id}",
            daemon=daemon,
        )
        self._thread.start()
        return self._thread

    def run(self) -> None:
        consumers = [
            threading.Thread(target=self._consume, name=f"tool-consumer-{index + 1}", daemon=True)
            for index in range(self.consumer_count)
        ]
        for consumer in consumers:
            consumer.start()

        retry_seconds = 1
        try:
            while not self._stop_event.is_set():
                try:
                    self._connection_session()
                    retry_seconds = 1
                except (OSError, TimeoutError, ValueError, WebSocketConnectionClosedException, WebSocketTimeoutException):
                    if self._stop_event.is_set():
                        break
                    logger.exception("provider connection lost; reconnecting in %ss", retry_seconds)
                    self._stop_event.wait(retry_seconds)
                    retry_seconds = min(retry_seconds * 2, 30)
        finally:
            for consumer in consumers:
                consumer.join(timeout=5)

    def stop(self, timeout: float = 5) -> None:
        self._stop_event.set()
        with self._state_lock:
            for cancellation in self.cancellations.values():
                cancellation.set()
        websocket = self._websocket
        if websocket:
            websocket.close()
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join(timeout=timeout)

    def _connection_session(self) -> None:
        websocket = create_connection(self.server_url, timeout=1, enable_multithread=True)
        self._websocket = websocket
        try:
            websocket.send(json.dumps({
                "type": "register",
                "provider_id": self.provider_id,
                "revision": self.revision,
                "tools": [tool.schema() for tool in self.tools.values()],
            }, ensure_ascii=False))
            registered = json.loads(websocket.recv())
            if registered.get("type") != "registered":
                raise ValueError(f"registration rejected: {registered}")
            logger.info("registered provider=%s tools=%s", self.provider_id, sorted(self.tools))

            next_heartbeat = time.monotonic() + self.heartbeat_seconds
            while not self._stop_event.is_set():
                self._flush_events(websocket)
                if time.monotonic() >= next_heartbeat:
                    websocket.send(json.dumps({"type": "ping"}))
                    next_heartbeat = time.monotonic() + self.heartbeat_seconds
                try:
                    raw_message = websocket.recv()
                except WebSocketTimeoutException:
                    continue
                if not raw_message:
                    raise WebSocketConnectionClosedException("provider connection closed")
                self._handle_message(json.loads(raw_message))
        finally:
            self._websocket = None
            websocket.close()

    def _flush_events(self, websocket: WebSocket) -> None:
        while True:
            try:
                event = self.events.get_nowait()
            except queue.Empty:
                return
            websocket.send(json.dumps(event, ensure_ascii=False))

    def _handle_message(self, message: dict[str, Any]) -> None:
        message_type = message.get("type")
        if message_type == "invoke":
            self._accept(message)
        elif message_type == "cancel":
            self._cancel(message.get("task_id"))
        elif message_type == "ping":
            self.events.put({"type": "pong"})

    def _accept(self, message: dict[str, Any]) -> None:
        task_id = message.get("task_id")
        tool_name = message.get("tool")
        if not task_id or tool_name not in self.tools:
            self.events.put({"type": "rejected", "task_id": task_id, "message": "unknown tool"})
            return
        cancellation = threading.Event()
        with self._state_lock:
            self.cancellations[task_id] = cancellation
        try:
            self.tasks.put_nowait(message)
        except queue.Full:
            with self._state_lock:
                self.cancellations.pop(task_id, None)
            self.events.put({"type": "rejected", "task_id": task_id, "message": "provider queue is full"})
            return
        self.events.put({"type": "accepted", "task_id": task_id})

    def _cancel(self, task_id: str | None) -> None:
        if not task_id:
            return
        with self._state_lock:
            cancellation = self.cancellations.get(task_id)
        if cancellation:
            cancellation.set()

    def _consume(self) -> None:
        while not self._stop_event.is_set():
            try:
                message = self.tasks.get(timeout=0.5)
            except queue.Empty:
                continue
            if message is None:
                self.tasks.task_done()
                return
            task_id = message["task_id"]
            try:
                self._execute(message)
            finally:
                with self._state_lock:
                    self.cancellations.pop(task_id, None)
                self.tasks.task_done()

    def _execute(self, message: dict[str, Any]) -> None:
        task_id = message["task_id"]
        tool = self.tools[message["tool"]]
        with self._state_lock:
            cancellation = self.cancellations[task_id]

        def report_progress(progress: float, status_message: str | None = None) -> None:
            self.events.put({
                "type": "status",
                "task_id": task_id,
                "status": "working",
                "progress": max(0.0, min(progress, 1.0)),
                "message": status_message,
            })

        context = ToolContext(
            task_id=task_id,
            deadline=message.get("deadline"),
            cancelled=cancellation.is_set,
            report_progress=report_progress,
        )
        if cancellation.is_set():
            return
        try:
            arguments = message.get("arguments", {})
            Draft202012Validator(tool.input_schema).validate(arguments)
            output = tool.execute(arguments, context)
            Draft202012Validator(tool.output_schema).validate(output)
            if cancellation.is_set():
                return
            self.events.put({"type": "result", "task_id": task_id, "success": True, "output": output})
        except Exception as error:
            logger.exception("tool execution failed task_id=%s tool=%s", task_id, tool.name)
            self.events.put({
                "type": "result",
                "task_id": task_id,
                "success": False,
                "error": {"code": type(error).__name__, "message": str(error)},
            })
