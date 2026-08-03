# agent/queue_client.py
import json
import os

import redis

REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_SOCKET_TIMEOUT = float(os.getenv("REDIS_SOCKET_TIMEOUT", "30"))

AGENT_QUEUE_NAME = os.getenv("AGENT_QUEUE_NAME", "agent_tasks")
AGENT_WORKER_STATUS_KEY = os.getenv(
    "AGENT_WORKER_STATUS_KEY",
    "aagent:worker:status",
)
AGENT_SYSTEM_PROMPT_KEY = os.getenv(
    "AGENT_SYSTEM_PROMPT_KEY",
    "aagent:settings:system_prompt",
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

def set_system_prompt(system_prompt: str):
    client = get_connection()
    client.set(AGENT_SYSTEM_PROMPT_KEY, system_prompt)
    return True

def get_system_prompt():
    client = get_connection()
    return client.get(AGENT_SYSTEM_PROMPT_KEY)

def pop_from_queue(queue_name: str, timeout: int = 5):
    client = get_connection()
    item = client.brpop(queue_name, timeout=timeout)
    if item is None:
        return None
    _, payload = item
    return json.loads(payload)