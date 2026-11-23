"""Client for Tool Server wait and async calls."""

from __future__ import annotations

import os
from typing import Any

import requests


class ToolServerError(RuntimeError):
    """Raised when a remote tool cannot produce a completed result."""

    def __init__(self, message: str, *, task_id: str | None = None) -> None:
        super().__init__(message)
        self.task_id = task_id


def get_remote_tool_schemas(tool_names: set[str]) -> list[dict[str, Any]]:
    """Fetch selected Remote Tool definitions and convert them to OpenAI format."""
    if not tool_names:
        return []
    base_url = os.getenv("TOOL_SERVER_URL", "http://tool_server:8083").rstrip("/")
    try:
        response = requests.get(f"{base_url}/api/tools", timeout=(3, 10))
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as error:
        raise ToolServerError(f"remote tool schema request failed: {error}") from error

    catalog = payload.get("tools", []) if isinstance(payload, dict) else []
    schemas = []
    for tool in catalog:
        if not isinstance(tool, dict) or tool.get("name") not in tool_names:
            continue
        schemas.append({
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool.get("description", ""),
                "parameters": tool.get("inputSchema", {"type": "object", "properties": {}}),
            },
        })
    found = {schema["function"]["name"] for schema in schemas}
    missing = sorted(tool_names - found)
    if missing:
        raise ToolServerError(f"remote tool schemas are unavailable: {', '.join(missing)}")
    return schemas


def call_remote_tool(
    tool: str,
    arguments: dict[str, Any],
    mode: str,
    timeout_ms: int,
    callback: dict[str, Any] | None = None,
) -> Any:
    # Validate against the live registry before submitting a wait or async task.
    get_remote_tool_schemas({tool})
    base_url = os.getenv("TOOL_SERVER_URL", "http://tool_server:8083").rstrip("/")
    request_body = {"arguments": arguments, "mode": mode, "timeout_ms": timeout_ms}
    if callback is not None:
        request_body["callback"] = callback
    try:
        response = requests.post(
            f"{base_url}/api/tools/{tool}/calls",
            json=request_body,
            timeout=(3, timeout_ms / 1000 + 5),
        )
    except requests.RequestException as error:
        raise ToolServerError(f"remote tool request failed: {error}") from error

    try:
        payload = response.json()
    except ValueError:
        payload = {}
    task_id = payload.get("task_id") if isinstance(payload, dict) else None
    detail = payload.get("detail") if isinstance(payload, dict) else None
    if response.status_code == 202 and mode == "async" and task_id:
        return task_id
    if response.status_code == 202:
        raise ToolServerError(
            f"remote tool did not complete; task continues on server: {task_id or 'unknown'}",
            task_id=task_id,
        )
    if response.status_code != 200:
        raise ToolServerError(
            f"remote tool request failed with HTTP {response.status_code}: {detail or payload}",
            task_id=task_id,
        )
    if not isinstance(payload, dict) or payload.get("status") != "completed":
        message = payload.get("error") if isinstance(payload, dict) else payload
        raise ToolServerError(f"remote tool failed: {message}", task_id=task_id)
    return payload.get("result")
