import json
import os

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
