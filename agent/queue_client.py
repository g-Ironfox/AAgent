# agent/queue_client.py
import json
import os

import redis

REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_SOCKET_TIMEOUT = float(os.getenv("REDIS_SOCKET_TIMEOUT", "30"))

MAIN_AGENT_QUEUE_NAME = os.getenv("MAIN_AGENT_QUEUE_NAME", "main_agent_queue")
AGENT_WORKER_STATUS_KEY = os.getenv(
    "AGENT_WORKER_STATUS_KEY",
    "aagent:worker:status",
)
# 整个设置以一个 JSON 对象存在单个 Key 下,运行时以 Redis 为唯一真源
AGENT_SETTINGS_KEY = os.getenv(
    "AGENT_SETTINGS_KEY",
    "aagent:settings",
)
# 旧版扁平 Key(仅首次启动迁移用,不写入)
AGENT_SYSTEM_PROMPT_KEY = os.getenv(
    "AGENT_SYSTEM_PROMPT_KEY",
    "aagent:settings:system_prompt",
)
AGENT_TOOLS_KEY = os.getenv(
    "AGENT_TOOLS_KEY",
    "aagent:tools",
)


def get_connection():
    return redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        decode_responses=True,
        socket_timeout=REDIS_SOCKET_TIMEOUT,
    )


def publish_to_queue(queue_name: str, message: dict):
    client = get_connection()
    client.lpush(queue_name, json.dumps(message, ensure_ascii=False))
    return True

def insert_to_queue(queue_name: str, *messages: dict):
    client = get_connection()
    client.rpush(queue_name, *[json.dumps(i, ensure_ascii=False) for i in messages])
    return True

def set_worker_status(status: dict):
    client = get_connection()
    client.set(
        AGENT_WORKER_STATUS_KEY,
        json.dumps(status, ensure_ascii=False),
    )
    return True

def get_settings() -> dict:
    client = get_connection()
    raw = client.get(AGENT_SETTINGS_KEY)
    if raw is None:
        return {}
    try:
        settings = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return settings if isinstance(settings, dict) else {}

def set_settings(settings: dict) -> bool:
    client = get_connection()
    client.set(AGENT_SETTINGS_KEY, json.dumps(settings, ensure_ascii=False))
    return True

def redis_reset_tools() -> bool:
    client = get_connection()
    client.delete(AGENT_TOOLS_KEY)
    return True

def redis_register_tool(tool_name: str, schema: dict) -> bool:
    client = get_connection()
    client.hset(
        AGENT_TOOLS_KEY,
        tool_name,
        json.dumps(schema, ensure_ascii=False),
    )
    return True

def pop_from_queue(queue_name: str, timeout: int = 5):
    client = get_connection()
    item = client.brpop(queue_name, timeout=timeout)
    if item is None:
        return None
    _, payload = item
    return json.loads(payload)