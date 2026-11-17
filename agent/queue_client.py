# agent/queue_client.py
import os
import json

import redis

REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_SOCKET_TIMEOUT = float(os.getenv("REDIS_SOCKET_TIMEOUT", "30"))

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
