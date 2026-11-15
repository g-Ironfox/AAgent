"""Local tools for managing files in the shared workspace."""

from __future__ import annotations

import os
from typing import Any
from urllib.parse import quote

import requests

from tools.tool import tool


def _request(method: str, path: str, **kwargs: Any) -> dict[str, Any]:
    base_url = os.getenv("WORKSPACE_API_URL", "http://webui_py:8081").rstrip("/")
    try:
        response = requests.request(
            method,
            f"{base_url}/api/files{path}",
            timeout=(3, 15),
            **kwargs,
        )
    except requests.RequestException as error:
        raise RuntimeError(f"workspace request failed: {error}") from error

    try:
        payload = response.json()
    except ValueError:
        payload = {}
    if not response.ok:
        detail = payload.get("error", payload.get("detail", payload))
        if response.status_code == 409:
            raise ValueError(f"workspace file revision conflict; read the file again: {detail}")
        if response.status_code == 404:
            raise ValueError(f"workspace file not found: {detail}")
        raise RuntimeError(f"workspace request failed with HTTP {response.status_code}: {detail}")
    if not isinstance(payload, dict):
        raise RuntimeError("workspace API returned an invalid response")
    return payload


@tool(
    "列出工作区文件（不包含文件内容）",
    {"type": "object", "properties": {}, "additionalProperties": False},
    name="workspace.list_files",
    output_schema={
        "type": "object",
        "properties": {
            "items": {"type": "array", "items": {"type": "object"}},
            "revision": {"type": "integer"},
        },
        "required": ["items", "revision"],
    },
)
def list_workspace_files() -> dict[str, Any]:
    return _request("GET", "")


@tool(
    "读取工作区文件内容和 revision",
    {
        "type": "object",
        "properties": {"file_id": {"type": "string", "minLength": 1}},
        "required": ["file_id"],
        "additionalProperties": False,
    },
    name="workspace.get_file",
    output_schema={"type": "object"},
)
def get_workspace_file(file_id: str) -> dict[str, Any]:
    return _request("GET", f"/{quote(file_id, safe='')}")


@tool(
    "在工作区创建文件",
    {
        "type": "object",
        "properties": {
            "name": {"type": "string", "minLength": 1, "maxLength": 200},
            "content": {"type": "string", "maxLength": 1_000_000},
        },
        "required": ["name"],
        "additionalProperties": False,
    },
    name="workspace.create_file",
    output_schema={"type": "object"},
)
def create_workspace_file(name: str, content: str = "") -> dict[str, Any]:
    return _request("POST", "", json={"name": name, "content": content})


@tool(
    "更新工作区文件名称或内容；必须使用最近读取到的 revision",
    {
        "type": "object",
        "properties": {
            "file_id": {"type": "string", "minLength": 1},
            "name": {"type": "string", "minLength": 1, "maxLength": 200},
            "content": {"type": "string", "maxLength": 1_000_000},
            "revision": {"type": "integer", "minimum": 1},
        },
        "required": ["file_id", "name", "content", "revision"],
        "additionalProperties": False,
    },
    name="workspace.update_file",
    output_schema={"type": "object"},
)
def update_workspace_file(
    file_id: str, name: str, content: str, revision: int
) -> dict[str, Any]:
    return _request(
        "PUT",
        f"/{quote(file_id, safe='')}",
        json={"name": name, "content": content, "revision": revision},
    )


@tool(
    "删除工作区文件；必须使用最近读取到的 revision",
    {
        "type": "object",
        "properties": {
            "file_id": {"type": "string", "minLength": 1},
            "revision": {"type": "integer", "minimum": 1},
        },
        "required": ["file_id", "revision"],
        "additionalProperties": False,
    },
    name="workspace.delete_file",
    output_schema={
        "type": "object",
        "properties": {
            "deleted": {"type": "boolean"},
            "file_id": {"type": "string"},
        },
        "required": ["deleted", "file_id"],
    },
)
def delete_workspace_file(file_id: str, revision: int) -> dict[str, Any]:
    return _request(
        "DELETE",
        f"/{quote(file_id, safe='')}",
        params={"revision": revision},
    )
