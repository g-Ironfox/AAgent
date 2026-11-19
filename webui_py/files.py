from fastapi import APIRouter, Path, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from file_store import FileConflictError, FileMissingError, FileNameConflictError, FileStore

MAX_FILE_NAME_CHARS = 200
MAX_FILE_CONTENT_CHARS = 1_000_000


class FileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=MAX_FILE_NAME_CHARS)
    content: str = Field(default="", max_length=MAX_FILE_CONTENT_CHARS)
    revision: int | None = Field(default=None, ge=1)


class FilePinRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pinned: bool
    revision: int = Field(ge=1)


class CheckpointRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)


def create_files_router(store: FileStore) -> APIRouter:
    router = APIRouter(prefix="/api/files")

    def validate_name(name: str):
        name = name.strip()
        if not name:
            return None, JSONResponse(status_code=400, content={"error": "文件名不能为空"})
        return name, None

    def missing_response():
        return JSONResponse(status_code=404, content={"error": "文件不存在或已被删除"})

    @router.get("")
    def list_files():
        return {"items": store.list_files(), "revision": store.revision}

    @router.get("/events")
    def list_file_events(
        before_seq: int | None = Query(default=None, ge=1),
        limit: int = Query(default=50, ge=1, le=100),
        file_id: str | None = None,
    ):
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
    ):
        items = store.list_checkpoints(before_seq=before_seq, limit=limit + 1, file_id=file_id)
        has_more = len(items) > limit
        items = items[:limit]
        return {
            "items": items,
            "has_more": has_more,
            "next_before_seq": items[-1]["seq"] if has_more and items else None,
        }

    @router.get("/checkpoints/tree")
    def checkpoint_tree():
        return store.checkpoint_tree()

    @router.get("/checkpoints/{seq}/diff")
    def checkpoint_diff(seq: int = Path(ge=0)):
        try:
            return store.checkpoint_diff(seq)
        except FileMissingError:
            return JSONResponse(status_code=404, content={"error": "Checkpoint not found"})

    @router.post("/checkpoints", status_code=201)
    def create_checkpoint(payload: CheckpointRequest):
        name = payload.name.strip()
        if not name:
            return JSONResponse(status_code=400, content={"error": "Checkpoint name cannot be empty"})
        return store.create_checkpoint(name)

    @router.post("/checkpoints/{seq}/restore")
    def restore_checkpoint(seq: int = Path(ge=0)):
        try:
            return store.restore_checkpoint(seq)
        except FileMissingError:
            return JSONResponse(status_code=404, content={"error": "Checkpoint not found"})
        except FileNameConflictError:
            return JSONResponse(status_code=409, content={"error": "Checkpoint 包含同名文件，无法恢复"})

    @router.post("", status_code=201)
    def create_file(payload: FileRequest):
        name, error = validate_name(payload.name)
        if error:
            return error
        try:
            return store.create_file(name, payload.content)
        except FileNameConflictError:
            return JSONResponse(status_code=409, content={"error": "同名文件已存在"})

    @router.get("/{file_id}")
    def get_file(file_id: str):
        try:
            return store.get_file(file_id)
        except FileMissingError:
            return missing_response()

    @router.put("/{file_id}")
    def update_file(file_id: str, payload: FileRequest):
        name, error = validate_name(payload.name)
        if error:
            return error
        if payload.revision is None:
            return JSONResponse(status_code=400, content={"error": "缺少文件 revision"})
        try:
            return store.update_file(file_id, name, payload.content, payload.revision)
        except FileMissingError:
            return missing_response()
        except FileNameConflictError:
            return JSONResponse(status_code=409, content={"error": "同名文件已存在"})
        except FileConflictError:
            return JSONResponse(status_code=409, content={"error": "文件已被其他操作修改，请刷新后重试"})

    @router.patch("/{file_id}/pin")
    def update_file_pin(file_id: str, payload: FilePinRequest):
        try:
            return store.set_pinned(file_id, payload.pinned, payload.revision)
        except FileMissingError:
            return missing_response()
        except FileConflictError:
            return JSONResponse(status_code=409, content={"error": "文件已被其他操作修改，请刷新后重试"})

    @router.delete("/{file_id}")
    def delete_file(file_id: str, revision: int):
        try:
            store.delete_file(file_id, revision)
            return {"deleted": True, "file_id": file_id}
        except FileMissingError:
            return missing_response()
        except FileConflictError:
            return JSONResponse(status_code=409, content={"error": "文件已被其他操作修改，请刷新后重试"})

    return router
