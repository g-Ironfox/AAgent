# qqbot/queue_client.py
import json
import os

import redis

REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))

AGENT_QUEUE_NAME = os.getenv("AGENT_QUEUE_NAME", "agent_tasks")


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