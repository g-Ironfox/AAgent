from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from pymongo import DESCENDING
from pymongo.collection import Collection
from pymongo.errors import PyMongoError

from common import parse_object_id

MAX_DOCUMENT_TITLE_CHARS = 200
MAX_DOCUMENT_CONTENT_CHARS = 1_000_000


class DocumentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=MAX_DOCUMENT_TITLE_CHARS)
    content: str = Field(default="", max_length=MAX_DOCUMENT_CONTENT_CHARS)


class DocumentPinRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pinned: bool


def document_response(document: dict[str, Any], include_content: bool = True) -> dict[str, Any]:
    response = {
        "id": str(document["_id"]),
        "title": document.get("title", ""),
        "pinned": bool(document.get("pinned", False)),
        "created_at": document.get("created_at"),
        "updated_at": document.get("updated_at"),
    }
    if include_content:
        response["content"] = document.get("content", "")
    return response


def create_documents_router(documents: Collection) -> APIRouter:
    router = APIRouter(prefix="/api/documents")

    @router.get("")
    def list_documents():
        try:
            items = documents.find({}, {"title": 1, "pinned": 1, "created_at": 1, "updated_at": 1}).sort(
                "updated_at", DESCENDING
            )
            return {"items": [document_response(item, include_content=False) for item in items]}
        except PyMongoError:
            return JSONResponse(status_code=503, content={"error": "文档列表暂时不可用"})

    @router.post("", status_code=201)
    def create_document(payload: DocumentRequest):
        title = payload.title.strip()
        if not title:
            return JSONResponse(status_code=400, content={"error": "文档标题不能为空"})
        now = datetime.now(timezone.utc)
        document = {"title": title, "content": payload.content, "pinned": False, "created_at": now, "updated_at": now}
        try:
            result = documents.insert_one(document)
        except PyMongoError:
            return JSONResponse(status_code=503, content={"error": "暂时无法创建文档"})
        document["_id"] = result.inserted_id
        return document_response(document)

    @router.get("/{document_id_value}")
    def get_document(document_id_value: str):
        object_id = parse_object_id(document_id_value, "文档 ID 无效")
        if isinstance(object_id, JSONResponse):
            return object_id
        try:
            document = documents.find_one({"_id": object_id})
        except PyMongoError:
            return JSONResponse(status_code=503, content={"error": "文档暂时不可用"})
        if document is None:
            return JSONResponse(status_code=404, content={"error": "文档不存在或已被删除"})
        return document_response(document)

    @router.put("/{document_id_value}")
    def update_document(document_id_value: str, payload: DocumentRequest):
        object_id = parse_object_id(document_id_value, "文档 ID 无效")
        if isinstance(object_id, JSONResponse):
            return object_id
        title = payload.title.strip()
        if not title:
            return JSONResponse(status_code=400, content={"error": "文档标题不能为空"})
        updated_at = datetime.now(timezone.utc)
        try:
            document = documents.find_one_and_update(
                {"_id": object_id},
                {"$set": {"title": title, "content": payload.content, "updated_at": updated_at}},
                return_document=True,
            )
        except PyMongoError:
            return JSONResponse(status_code=503, content={"error": "暂时无法保存文档"})
        if document is None:
            return JSONResponse(status_code=404, content={"error": "文档不存在或已被删除"})
        return document_response(document)

    @router.patch("/{document_id_value}/pin")
    def update_document_pin(document_id_value: str, payload: DocumentPinRequest):
        object_id = parse_object_id(document_id_value, "文档 ID 无效")
        if isinstance(object_id, JSONResponse):
            return object_id
        try:
            document = documents.find_one_and_update(
                {"_id": object_id},
                {"$set": {"pinned": payload.pinned}},
                return_document=True,
            )
        except PyMongoError:
            return JSONResponse(status_code=503, content={"error": "暂时无法更新文档钉住状态"})
        if document is None:
            return JSONResponse(status_code=404, content={"error": "文档不存在或已被删除"})
        return document_response(document)

    @router.delete("/{document_id_value}")
    def delete_document(document_id_value: str):
        object_id = parse_object_id(document_id_value, "文档 ID 无效")
        if isinstance(object_id, JSONResponse):
            return object_id
        try:
            result = documents.delete_one({"_id": object_id})
        except PyMongoError:
            return JSONResponse(status_code=503, content={"error": "暂时无法删除文档"})
        if result.deleted_count == 0:
            return JSONResponse(status_code=404, content={"error": "文档不存在或已被删除"})
        return {"deleted": True, "id": document_id_value}

    return router