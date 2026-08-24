from typing import Any

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from pymongo.collection import Collection
from pymongo.errors import PyMongoError


class AgentSettingsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workflow_id: str | None = None


def create_settings_router(settings: Collection, workflows: Collection) -> APIRouter:
    router = APIRouter()

    @router.get("/api/settings")
    def get_settings():
        try:
            document = settings.find_one({"_id": "agent"}) or {}
        except PyMongoError:
            return JSONResponse(status_code=503, content={"error": "设置暂时不可用"})
        workflow_id = document.get("workflow_id")
        return {"workflow_id": str(workflow_id) if isinstance(workflow_id, ObjectId) else None}

    @router.put("/api/settings")
    def update_settings(payload: AgentSettingsRequest):
        workflow_id: ObjectId | None = None
        if payload.workflow_id:
            try:
                workflow_id = ObjectId(payload.workflow_id)
            except (InvalidId, TypeError):
                return JSONResponse(status_code=400, content={"error": "Workflow id 无效"})
            try:
                if workflows.find_one({"_id": workflow_id}, {"_id": 1}) is None:
                    return JSONResponse(status_code=404, content={"error": "Workflow 不存在或已被删除"})
            except PyMongoError:
                return JSONResponse(status_code=503, content={"error": "Workflow 暂时不可用"})
        try:
            document = settings.find_one_and_update(
                {"_id": "agent"},
                {"$set": {"workflow_id": workflow_id}},
                upsert=True,
                return_document=True,
            )
        except PyMongoError:
            return JSONResponse(status_code=503, content={"error": "设置保存失败"})
        return {"workflow_id": str(document["workflow_id"]) if document.get("workflow_id") else None}

    return router