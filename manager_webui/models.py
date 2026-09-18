from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from pymongo import DESCENDING
from pymongo.collection import Collection
from pymongo.errors import DuplicateKeyError, PyMongoError

from common import parse_object_id


class ModelRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    provider: str = Field(min_length=1, max_length=120)
    model: str = Field(min_length=1, max_length=200)
    base_url: str = Field(min_length=1, max_length=500)
    api_key: str = Field(default="", max_length=1000)
    enabled: bool = True


def model_response(document: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(document["_id"]),
        "name": document.get("name", ""),
        "provider": document.get("provider", ""),
        "model": document.get("model", ""),
        "base_url": document.get("base_url", ""),
        "api_key": document.get("api_key", ""),
        "enabled": bool(document.get("enabled", True)),
        "created_at": document.get("created_at"),
        "updated_at": document.get("updated_at"),
    }


def normalized_model(payload: ModelRequest) -> dict[str, Any]:
    values = payload.model_dump()
    values["name"] = values["name"].strip()
    values["provider"] = values["provider"].strip()
    values["model"] = values["model"].strip()
    values["base_url"] = values["base_url"].strip().rstrip("/")
    return values


def create_models_router(model_configs: Collection) -> APIRouter:
    router = APIRouter(prefix="/api/models")

    @router.get("")
    def list_models():
        try:
            items = model_configs.find({}).sort("updated_at", DESCENDING)
            return {"items": [model_response(item) for item in items]}
        except PyMongoError:
            return JSONResponse(status_code=503, content={"error": "模型配置暂时不可用"})

    @router.post("", status_code=201)
    def create_model(payload: ModelRequest):
        values = normalized_model(payload)
        if not all(values[field] for field in ("name", "provider", "model", "base_url")):
            return JSONResponse(status_code=400, content={"error": "模型名称、厂商、模型标识和 Base URL 不能为空"})
        now = datetime.now(timezone.utc)
        values.update({"created_at": now, "updated_at": now})
        try:
            if model_configs.find_one({"name": values["name"]}, {"_id": 1}):
                return JSONResponse(status_code=409, content={"error": "模型名称已存在"})
            result = model_configs.insert_one(values)
        except DuplicateKeyError:
            return JSONResponse(status_code=409, content={"error": "模型名称已存在"})
        except PyMongoError:
            return JSONResponse(status_code=503, content={"error": "暂时无法创建模型配置"})
        values["_id"] = result.inserted_id
        return model_response(values)

    @router.put("/{model_id_value}")
    def update_model(model_id_value: str, payload: ModelRequest):
        object_id = parse_object_id(model_id_value, "文档 ID 无效")
        if isinstance(object_id, JSONResponse):
            return object_id
        values = normalized_model(payload)
        if not all(values[field] for field in ("name", "provider", "model", "base_url")):
            return JSONResponse(status_code=400, content={"error": "模型名称、厂商、模型标识和 Base URL 不能为空"})
        values["updated_at"] = datetime.now(timezone.utc)
        try:
            if model_configs.find_one({"name": values["name"], "_id": {"$ne": object_id}}, {"_id": 1}):
                return JSONResponse(status_code=409, content={"error": "模型名称已存在"})
            document = model_configs.find_one_and_update(
                {"_id": object_id},
                {"$set": values},
                return_document=True,
            )
        except DuplicateKeyError:
            return JSONResponse(status_code=409, content={"error": "模型名称已存在"})
        except PyMongoError:
            return JSONResponse(status_code=503, content={"error": "暂时无法保存模型配置"})
        if document is None:
            return JSONResponse(status_code=404, content={"error": "模型配置不存在或已被删除"})
        return model_response(document)

    @router.delete("/{model_id_value}")
    def delete_model(model_id_value: str):
        object_id = parse_object_id(model_id_value, "文档 ID 无效")
        if isinstance(object_id, JSONResponse):
            return object_id
        try:
            result = model_configs.delete_one({"_id": object_id})
        except PyMongoError:
            return JSONResponse(status_code=503, content={"error": "暂时无法删除模型配置"})
        if result.deleted_count == 0:
            return JSONResponse(status_code=404, content={"error": "模型配置不存在或已被删除"})
        return {"deleted": True, "id": model_id_value}

    return router