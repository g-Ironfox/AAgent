"""Local tools for managing files in the shared workspace."""

from __future__ import annotations

import os
from typing import Any
from urllib.parse import quote

import requests

from tools.tool import tool


def _request(method: str, path: str, **kwargs: Any) -> dict[str, Any]:
    base_url = os.getenv("WORKSPACE_API_URL", "http://webui_py:8081").rstrip("/")
    headers = dict(kwargs.pop("headers", {}))
    try:
        from workflow_nodes import current_workflow_process

        process = current_workflow_process.get()
    except ImportError:
        process = None
    if process and process.get("process_id"):
        headers["X-AAgent-Process-ID"] = (
            f"{process['process_id']}:{process['_workspace_token']}"
        )
    try:
        response = requests.request(
            method,
            f"{base_url}/api/files{path}",
            timeout=(3, 15),
            headers=headers,
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
            resource = "checkpoint" if path.startswith("/checkpoints/") else "file"
            raise ValueError(f"workspace {resource} not found: {detail}")
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


@tool(
    "分页列出工作区 checkpoint，可按文件筛选；使用 next_before_seq 获取下一页",
    {
        "type": "object",
        "properties": {
            "before_seq": {"type": "integer", "minimum": 1},
            "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 50},
            "file_id": {"type": "string"},
        },
        "additionalProperties": False,
    },
    name="workspace.list_checkpoints",
    output_schema={
        "type": "object",
        "properties": {
            "items": {"type": "array", "items": {"type": "object"}},
            "has_more": {"type": "boolean"},
            "next_before_seq": {"type": ["integer", "null"]},
        },
        "required": ["items", "has_more", "next_before_seq"],
    },
)
def list_workspace_checkpoints(
    before_seq: int | None = None, limit: int = 50, file_id: str | None = None
) -> dict[str, Any]:
    params: dict[str, Any] = {"limit": limit}
    if before_seq is not None:
        params["before_seq"] = before_seq
    if file_id is not None:
        params["file_id"] = file_id
    return _request("GET", "/checkpoints", params=params)


@tool(
    "读取工作区 checkpoint 分支树及当前 head_seq",
    {"type": "object", "properties": {}, "additionalProperties": False},
    name="workspace.checkpoint_tree",
    output_schema={
        "type": "object",
        "properties": {
            "items": {"type": "array", "items": {"type": "object"}},
            "head_seq": {"type": ["integer", "null"]},
        },
        "required": ["items", "head_seq"],
    },
)
def get_workspace_checkpoint_tree() -> dict[str, Any]:
    return _request("GET", "/checkpoints/tree")


@tool(
    "获取 checkpoint 的父序号用于回滚；省略 seq 时查询当前 head。parent_seq=0 表示空工作区，可传给 restore_checkpoint；null 表示已无父 checkpoint",
    {
        "type": "object",
        "properties": {"seq": {"type": "integer", "minimum": 0}},
        "additionalProperties": False,
    },
    name="workspace.get_parent_checkpoint",
    output_schema={
        "type": "object",
        "properties": {
            "seq": {"type": "integer", "minimum": 0},
            "parent_seq": {"type": ["integer", "null"], "minimum": 0},
        },
        "required": ["seq", "parent_seq"],
    },
)
def get_parent_workspace_checkpoint(seq: int | str | None = None) -> dict[str, Any]:
    # Local workflow ports carry content strings; JSON Tool calls carry integers.
    if isinstance(seq, str):
        seq = int(seq)
    if seq is not None and (isinstance(seq, bool) or not isinstance(seq, int) or seq < 0):
        raise ValueError("checkpoint seq must be a non-negative integer")
    tree = get_workspace_checkpoint_tree()
    if seq is None:
        seq = tree["head_seq"] or 0
    if seq == 0:
        return {"seq": 0, "parent_seq": None}
    for checkpoint in tree["items"]:
        if checkpoint["seq"] == seq:
            return {"seq": seq, "parent_seq": checkpoint["data"]["parent_seq"] or 0}
    raise ValueError(f"workspace checkpoint not found: {seq}")


@tool(
    "读取 checkpoint 相对于父 checkpoint 的文件差异；seq=0 表示空工作区",
    {
        "type": "object",
        "properties": {"seq": {"type": "integer", "minimum": 0}},
        "required": ["seq"],
        "additionalProperties": False,
    },
    name="workspace.checkpoint_diff",
    output_schema={
        "type": "object",
        "properties": {
            "seq": {"type": "integer"},
            "parent_seq": {"type": ["integer", "null"]},
            "changes": {"type": "array", "items": {"type": "object"}},
        },
        "required": ["seq", "parent_seq", "changes"],
    },
)
def get_workspace_checkpoint_diff(seq: int) -> dict[str, Any]:
    return _request("GET", f"/checkpoints/{seq}/diff")


@tool(
    "为当前工作区全部文件创建命名 checkpoint",
    {
        "type": "object",
        "properties": {"name": {"type": "string", "minLength": 1, "maxLength": 200}},
        "required": ["name"],
        "additionalProperties": False,
    },
    name="workspace.create_checkpoint",
    output_schema={"type": "object"},
)
def create_workspace_checkpoint(name: str) -> dict[str, Any]:
    return _request("POST", "/checkpoints", json={"name": name})


@tool(
    "将整个工作区恢复到指定 checkpoint，文件 revision 会更新；seq=0 会清空工作区",
    {
        "type": "object",
        "properties": {"seq": {"type": "integer", "minimum": 0}},
        "required": ["seq"],
        "additionalProperties": False,
    },
    name="workspace.restore_checkpoint",
    output_schema={"type": "object"},
)
def restore_workspace_checkpoint(seq: int) -> dict[str, Any]:
    return _request("POST", f"/checkpoints/{seq}/restore")


@tool(
    "读取指定文件的逐级恢复计划：沿 checkpoint 当前分支跳过重复版本，以固定 stable 文件为底线；只读取，不执行恢复",
    {
        "type": "object",
        "properties": {
            "file_id": {"type": "string", "minLength": 1},
            "stable_file_id": {"type": "string", "minLength": 1},
            "checkpoint_seq": {"type": "integer", "minimum": 0},
        },
        "required": ["file_id", "stable_file_id", "checkpoint_seq"],
        "additionalProperties": False,
    },
    name="workspace.get_file_recovery_plan",
    output_schema={
        "type": "object",
        "properties": {"versions": {"type": "array", "items": {
            "type": "object", "properties": {
                "content": {"type": "string"}, "checkpoint_seq": {"type": "integer", "minimum": 0},
                "source": {"enum": ["checkpoint", "stable"]},
            }, "required": ["content", "checkpoint_seq", "source"], "additionalProperties": False,
        }}},
        "required": ["versions"],
    },
)
def get_file_recovery_plan(file_id: str, stable_file_id: str, checkpoint_seq: int) -> dict[str, Any]:
    from workflow_recovery import build_file_recovery_plan

    return build_file_recovery_plan(file_id, stable_file_id, checkpoint_seq, _request)
