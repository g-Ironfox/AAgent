import hmac
import logging
from typing import Any, Callable

from fastapi import APIRouter, Header, Path, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from file_store import FileConflictError, FileMissingError, FileNameConflictError, FileStore
from permissions import (
    can_access, can_access_checkpoint, normalize_checkpoint_permissions, normalize_permissions, process_levels,
)

logger = logging.getLogger(__name__)

MAX_FILE_NAME_CHARS = 200
MAX_FILE_CONTENT_CHARS = 1_000_000


class FileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=MAX_FILE_NAME_CHARS)
    content: str = Field(default="", max_length=MAX_FILE_CONTENT_CHARS)
    revision: int | None = Field(default=None, ge=1)
    permissions: "FilePermissions | None" = None


class PermissionLevels(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    read: int = Field(ge=0)
    write: int = Field(ge=0)


class CheckpointPermissions(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    read: bool = False
    create: bool = False
    restore: bool = False


class FilePermissions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    runtime: PermissionLevels
    required: PermissionLevels
    checkpoints: CheckpointPermissions = Field(default_factory=CheckpointPermissions)


class FilePinRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pinned: bool
    revision: int = Field(ge=1)


class CheckpointRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)


def create_files_router(
    store: FileStore,
    process_lookup: Callable[[str], dict[str, Any] | None] | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/api/files")

    def principal(process_identity: str | None):
        if not isinstance(process_identity, str) or not process_identity:
            return None, None
        if process_lookup is None:
            return None, JSONResponse(status_code=403, content={"error": "process identity is not available"})
        try:
            process_id, token = process_identity.rsplit(":", 1)
        except ValueError:
            return None, JSONResponse(status_code=403, content={"error": "invalid process identity"})
        try:
            process = process_lookup(process_id)
        except Exception:
            logger.exception("failed to validate workspace process identity")
            return None, JSONResponse(status_code=503, content={"error": "process authorization unavailable"})
        if (
            not isinstance(process, dict)
            or process.get("process_id") != process_id
            or process.get("process_type") != "workflow"
            or not isinstance(process.get("_workspace_token"), str)
            or not hmac.compare_digest(process["_workspace_token"].encode(), token.encode())
            or process.get("status") in {"completed", "failed", "terminated", "killed", "lost"}
        ):
            return None, JSONResponse(status_code=403, content={"error": "invalid process identity"})
        return process, None

    def admin_only(process):
        if process is not None:
            return JSONResponse(status_code=403, content={"error": "workspace history is admin-only"})
        return None

    def checkpoint_access(process, operation):
        if not can_access_checkpoint(process, operation):
            return JSONResponse(status_code=403, content={"error": f"checkpoint {operation} permission denied"})
        return None

    def readable_change(process, change):
        if process is None:
            return True
        for side in ("before_permissions", "after_permissions"):
            if not can_access(process, {"permissions": change.get(side)}, "read"):
                return False
        try:
            current = store.get_file(change["file_id"])
        except FileMissingError:
            return True
        return can_access(process, current, "read")

    def denied(operation: str):
        return JSONResponse(status_code=403, content={"error": f"file {operation} permission denied"})

    def validate_name(name: str):
        name = name.strip()
        if not name:
            return None, JSONResponse(status_code=400, content={"error": "文件名不能为空"})
        return name, None

    def missing_response():
        return JSONResponse(status_code=404, content={"error": "文件不存在或已被删除"})

    @router.get("")
    def list_files(process_id: str | None = Header(default=None, alias="X-AAgent-Process-ID")):
        process, error = principal(process_id)
        if error:
            return error
        items = [file for file in store.list_files() if can_access(process, file, "read")]
        return {"items": items, "revision": store.revision}

    @router.get("/events")
    def list_file_events(
        before_seq: int | None = Query(default=None, ge=1),
        limit: int = Query(default=50, ge=1, le=100),
        file_id: str | None = None,
        process_id: str | None = Header(default=None, alias="X-AAgent-Process-ID"),
    ):
        process, error = principal(process_id)
        if error:
            return error
        if response := admin_only(process):
            return response
        items = store.list_events(before_seq=before_seq, limit=limit + 1, file_id=file_id)
        has_more = len(items) > limit
        items = items[:limit]
        return {
            "items": items,
            "has_more": has_more,
            "next_before_seq": items[-1]["seq"] if has_more and items else None,
        }

    @router.get("/checkpoints")
    def list_checkpoints(
        before_seq: int | None = Query(default=None, ge=1),
        limit: int = Query(default=50, ge=1, le=100),
        file_id: str | None = None,
        process_id: str | None = Header(default=None, alias="X-AAgent-Process-ID"),
    ):
        process, error = principal(process_id)
        if error:
            return error
        if response := checkpoint_access(process, "read"):
            return response
        items = store.list_checkpoints(before_seq=before_seq, limit=limit + 1, file_id=file_id)
        has_more = len(items) > limit
        items = items[:limit]
        return {
            "items": items,
            "has_more": has_more,
            "next_before_seq": items[-1]["seq"] if has_more and items else None,
        }

    @router.get("/checkpoints/tree")
    def checkpoint_tree(process_id: str | None = Header(default=None, alias="X-AAgent-Process-ID")):
        process, error = principal(process_id)
        if error:
            return error
        if response := checkpoint_access(process, "read"):
            return response
        return store.checkpoint_tree()

    @router.get("/checkpoints/{seq}/diff")
    def checkpoint_diff(seq: int = Path(ge=0), process_id: str | None = Header(default=None, alias="X-AAgent-Process-ID")):
        process, error = principal(process_id)
        if error:
            return error
        if response := checkpoint_access(process, "read"):
            return response
        try:
            result = store.checkpoint_diff(seq)
            result["changes"] = [change for change in result["changes"] if readable_change(process, change)]
            return result
        except FileMissingError:
            return JSONResponse(status_code=404, content={"error": "Checkpoint not found"})

    @router.post("/checkpoints", status_code=201)
    def create_checkpoint(payload: CheckpointRequest, process_id: str | None = Header(default=None, alias="X-AAgent-Process-ID")):
        process, error = principal(process_id)
        if error:
            return error
        if response := checkpoint_access(process, "create"):
            return response
        name = payload.name.strip()
        if not name:
            return JSONResponse(status_code=400, content={"error": "Checkpoint name cannot be empty"})
        event = store.create_checkpoint(name)
        if process is not None:
            event["data"] = {key: value for key, value in event["data"].items() if key not in {"files", "changes"}}
        return event

    @router.post("/checkpoints/{seq}/restore")
    def restore_checkpoint(seq: int = Path(ge=0), process_id: str | None = Header(default=None, alias="X-AAgent-Process-ID")):
        process, error = principal(process_id)
        if error:
            return error
        if response := checkpoint_access(process, "restore"):
            return response
        try:
            return store.restore_checkpoint(seq)
        except FileMissingError:
            return JSONResponse(status_code=404, content={"error": "Checkpoint not found"})
        except FileNameConflictError:
            return JSONResponse(status_code=409, content={"error": "Checkpoint 包含同名文件，无法恢复"})

    @router.post("", status_code=201)
    def create_file(payload: FileRequest, process_id: str | None = Header(default=None, alias="X-AAgent-Process-ID")):
        process, error = principal(process_id)
        if error:
            return error
        name, error = validate_name(payload.name)
        if error:
            return error
        if process is None:
            try:
                permissions = normalize_permissions(
                    payload.permissions.model_dump() if payload.permissions else None
                )
            except ValueError as error:
                return JSONResponse(status_code=422, content={"error": str(error)})
        else:
            if payload.permissions is not None:
                return denied("permission metadata update")
            levels = process_levels(process)
            permissions = {
                "runtime": dict(levels), "required": dict(levels),
                "checkpoints": normalize_checkpoint_permissions(process.get("permissions", {}).get("checkpoints")),
            }
        try:
            return store.create_file(name, payload.content, permissions)
        except FileNameConflictError:
            return JSONResponse(status_code=409, content={"error": "同名文件已存在"})

    @router.get("/{file_id}")
    def get_file(file_id: str, process_id: str | None = Header(default=None, alias="X-AAgent-Process-ID")):
        process, error = principal(process_id)
        if error:
            return error
        try:
            file = store.get_file(file_id)
            if not can_access(process, file, "read"):
                return denied("read")
            return file
        except FileMissingError:
            return missing_response()

    @router.put("/{file_id}")
    def update_file(file_id: str, payload: FileRequest, process_id: str | None = Header(default=None, alias="X-AAgent-Process-ID")):
        process, error = principal(process_id)
        if error:
            return error
        name, error = validate_name(payload.name)
        if error:
            return error
        if payload.revision is None:
            return JSONResponse(status_code=400, content={"error": "缺少文件 revision"})
        if process is not None and payload.permissions is not None:
            return denied("permission metadata update")
        try:
            current = store.get_file(file_id)
            if not can_access(process, current, "write"):
                return denied("write")
            permissions = None
            if process is None and payload.permissions is not None:
                permissions = normalize_permissions(payload.permissions.model_dump())
            return store.update_file(file_id, name, payload.content, payload.revision, permissions)
        except FileMissingError:
            return missing_response()
        except FileNameConflictError:
            return JSONResponse(status_code=409, content={"error": "同名文件已存在"})
        except FileConflictError:
            return JSONResponse(status_code=409, content={"error": "文件已被其他操作修改，请刷新后重试"})
        except ValueError as error:
            return JSONResponse(status_code=422, content={"error": str(error)})

    @router.patch("/{file_id}/pin")
    def update_file_pin(file_id: str, payload: FilePinRequest, process_id: str | None = Header(default=None, alias="X-AAgent-Process-ID")):
        process, error = principal(process_id)
        if error:
            return error
        try:
            current = store.get_file(file_id)
            if not can_access(process, current, "write"):
                return denied("write")
            updated = store.set_pinned(file_id, payload.pinned, payload.revision)
            if not can_access(process, updated, "read"):
                updated.pop("content", None)
            return updated
        except FileMissingError:
            return missing_response()
        except FileConflictError:
            return JSONResponse(status_code=409, content={"error": "文件已被其他操作修改，请刷新后重试"})

    @router.delete("/{file_id}")
    def delete_file(file_id: str, revision: int, process_id: str | None = Header(default=None, alias="X-AAgent-Process-ID")):
        process, error = principal(process_id)
        if error:
            return error
        try:
            current = store.get_file(file_id)
            if not can_access(process, current, "write"):
                return denied("write")
            store.delete_file(file_id, revision)
            return {"deleted": True, "file_id": file_id}
        except FileMissingError:
            return missing_response()
        except FileConflictError:
            return JSONResponse(status_code=409, content={"error": "文件已被其他操作修改，请刷新后重试"})

    return router
