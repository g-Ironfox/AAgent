# agent/queue_client.py
import json
import os

from redis_client import get_connection

AGENT_TOOLS_KEY = os.getenv(
    "AGENT_TOOLS_KEY",
    "aagent:tools",
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
