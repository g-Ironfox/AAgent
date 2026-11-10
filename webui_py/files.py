from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from file_store import FileConflictError, FileMissingError, FileStore

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

    @router.post("", status_code=201)
    def create_file(payload: FileRequest):
        name, error = validate_name(payload.name)
        if error:
            return error
        return store.create_file(name, payload.content)

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
