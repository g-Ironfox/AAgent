from copy import deepcopy

from fastapi import APIRouter


EVENT_CATALOG = [
    {
        "event_type": "qq",
        "scope": "main_queue",
        "title": "QQ 输入",
        "description": "QQ listener 产生，经 QQ consumer 筛选后进入主队列。",
        "producer": "qqbot/listener.py",
        "consumer": "agent/task_worker.py",
        "schema": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "required": ["event_type", "payload"],
            "properties": {
                "event_type": {"const": "qq"},
                "payload": {
                    "type": "object",
                    "required": ["post_type", "user_id"],
                    "properties": {
                        "post_type": {"enum": ["message", "inputing"]},
                        "user_id": {"type": "integer"},
                        "group_id": {"type": ["integer", "null"]},
                        "raw_message": {"type": "string"},
                        "message": {"type": "array", "items": {"type": "object"}},
                    },
                    "additionalProperties": True,
                },
            },
            "additionalProperties": True,
        },
    },
    {
        "event_type": "terminal",
        "scope": "main_queue",
        "title": "终端输入",
        "description": "WebUI 终端提交的用户消息，转换为 workflow 事件。",
        "producer": "webui_py/events.py",
        "consumer": "agent/task_worker.py",
        "schema": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "required": ["event_type", "payload"],
            "properties": {
                "event_type": {"const": "terminal"},
                "time": {"type": "string", "format": "date-time"},
                "payload": {
                    "type": "object",
                    "required": ["message", "files"],
                    "properties": {
                        "message": {"type": "string", "minLength": 1, "maxLength": 4000},
                        "files": {"type": "array", "maxItems": 0},
                    },
                    "additionalProperties": False,
                },
            },
            "additionalProperties": True,
        },
    },
    {
        "event_type": "workflow",
        "scope": "main_queue",
        "title": "Workflow 执行",
        "description": "触发当前激活 Workflow，并按输入端口名称传播 payload。",
        "producer": "agent/task_worker.py",
        "consumer": "agent/task_worker.py",
        "schema": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "required": ["event_type", "payload"],
            "properties": {
                "event_type": {"const": "workflow"},
                "payload": {
                    "type": "object",
                    "required": ["content", "source"],
                    "properties": {
                        "content": {},
                        "source": {"enum": ["qq", "terminal"]},
                    },
                    "additionalProperties": True,
                },
            },
            "additionalProperties": True,
        },
    },
    {
        "event_type": "response",
        "scope": "main_queue",
        "title": "Workflow 响应",
        "description": "记录 Workflow 最终输出，不执行额外业务处理。",
        "producer": "agent/task_worker.py",
        "consumer": "agent/task_worker.py",
        "schema": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "required": ["event_type", "payload"],
            "properties": {
                "event_type": {"const": "response"},
                "payload": {
                    "type": "object",
                    "required": ["content"],
                    "properties": {"content": {}},
                    "additionalProperties": False,
                },
            },
            "additionalProperties": True,
        },
    },
    {
        "event_type": "async_result",
        "scope": "callback_queue",
        "title": "异步 Tool 回调",
        "description": "Tool Server 投递到专用 Redis 队列，不属于主 Agent 队列协议。",
        "producer": "tool_server",
        "consumer": "专用回调消费者",
        "schema": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "required": ["event_type", "payload"],
            "properties": {
                "event_type": {"const": "async_result"},
                "payload": {
                    "type": "object",
                    "required": ["task_id", "tool", "status", "result", "error", "progress", "message"],
                    "properties": {
                        "task_id": {"type": "string"},
                        "tool": {"type": "string"},
                        "status": {"enum": ["completed", "failed"]},
                        "result": {},
                        "error": {"type": ["string", "null"]},
                        "progress": {},
                        "message": {"type": ["string", "null"]},
                    },
                    "additionalProperties": False,
                },
            },
            "additionalProperties": False,
        },
    },
    {
        "event_type": "raw",
        "scope": "display_only",
        "title": "原始队列内容",
        "description": "WebUI 为无法解析成 JSON 对象的内容提供的展示包装，不会进入主 worker。",
        "producer": "webui_py/events.py",
        "consumer": "WebUI",
        "schema": {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "required": ["event_type", "payload"],
            "properties": {
                "event_type": {"const": "raw"},
                "payload": {
                    "type": "object",
                    "required": ["raw"],
                    "properties": {"raw": {"type": "string"}},
                    "additionalProperties": False,
                },
            },
            "additionalProperties": False,
        },
    },
]


def event_catalog() -> dict:
    return {"items": deepcopy(EVENT_CATALOG), "count": len(EVENT_CATALOG)}


def create_event_catalog_router() -> APIRouter:
    router = APIRouter()

    @router.get("/api/event-catalog")
    def get_event_catalog():
        return event_catalog()

    return router