import json
import os

import redis

REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
QQ_AGENT_QUEUE_NAME = os.getenv("QQ_AGENT_QUEUE_NAME", "subagent:qq:tasks")
MAIN_AGENT_QUEUE_NAME = os.getenv("MAIN_AGENT_QUEUE_NAME", "main_agent_queue")
QQ_WORKER_STATUS_KEY = os.getenv("QQ_AGENT_WORKER_STATUS_KEY", "subagent:qq:worker:status")
QQ_AGENT_SETTINGS_KEY = os.getenv("QQ_AGENT_SETTINGS_KEY", "subagent:qq:settings")


def get_connection():
    return redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)


def publish_to_queue(queue_name: str, message: dict):
    client = get_connection()
    client.lpush(queue_name, json.dumps(message, ensure_ascii=False))
    return True


def pop_from_queue(queue_name: str, timeout: int = 5):
    client = get_connection()
    item = client.blpop(queue_name, timeout=timeout)
    if item is None:
        return None
    _, payload = item
    return json.loads(payload)


def set_worker_status(status: dict):
    client = get_connection()
    client.set(QQ_WORKER_STATUS_KEY, json.dumps(status, ensure_ascii=False))


def get_agent_settings():
    raw = get_connection().get(QQ_AGENT_SETTINGS_KEY)
    if not raw:
        return {"document_ids": []}
    settings = json.loads(raw)
    return settings if isinstance(settings, dict) else {"document_ids": []}
