import re
from typing import Any

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from pymongo import ReturnDocument
from pymongo.collection import Collection
from pymongo.errors import DuplicateKeyError, PyMongoError

EVENT_TYPE_PATTERN = re.compile(r"^[a-z][a-z0-9_.-]*$")
MAX_EVENT_TYPE_LENGTH = 80


class EventBindingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_type: str = Field(min_length=1, max_length=MAX_EVENT_TYPE_LENGTH)
    workflow_id: str = Field(min_length=1)
    enabled: bool = True


def _binding_response(document: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(document["_id"]),
        "event_type": document.get("event_type", ""),
        "workflow_id": str(document["workflow_id"]) if isinstance(document.get("workflow_id"), ObjectId) else None,
        "workflow_name": document.get("workflow_name", ""),
        "enabled": document.get("enabled", True),
        "created_at": document.get("created_at"),
        "updated_at": document.get("updated_at"),
    }


def create_event_bindings_router(bindings: Collection, workflows: Collection) -> APIRouter:
    router = APIRouter()

    @router.get("/api/event-bindings/workflow-options")
    def list_workflow_options():
        try:
            items = workflows.find({}, {"name": 1, "input_ports": 1, "output_ports": 1}).sort("name", 1)
            return {
                "items": [
                    {
                        "id": str(item["_id"]),
                        "name": item.get("name", ""),
                        "input_ports": item.get("input_ports", []),
                        "output_ports": item.get("output_ports", []),
                    }
                    for item in items
                ]
            }
        except PyMongoError:
            return JSONResponse(status_code=503, content={"error": "Workflow 选项暂时不可用"})

    def parse_request(payload: EventBindingRequest) -> tuple[dict[str, Any] | None, JSONResponse | None]:
        event_type = payload.event_type.strip().lower()
        if not EVENT_TYPE_PATTERN.fullmatch(event_type):
            return None, JSONResponse(status_code=400, content={"error": "Event 类型只能包含小写字母、数字、点、下划线和短横线"})
        try:
            workflow_id = ObjectId(payload.workflow_id)
        except (InvalidId, TypeError):
            return None, JSONResponse(status_code=400, content={"error": "Workflow id 无效"})
        workflow = workflows.find_one({"_id": workflow_id}, {"name": 1})
        if workflow is None:
            return None, JSONResponse(status_code=404, content={"error": "Workflow 不存在或已被删除"})
        return {
            "event_type": event_type,
            "workflow_id": workflow_id,
            "workflow_name": workflow.get("name", ""),
            "enabled": payload.enabled,
        }, None

    @router.get("/api/event-bindings")
    def list_event_bindings():
        try:
            items = bindings.find({}).sort("event_type", 1)
            return {"items": [_binding_response(item) for item in items]}
        except PyMongoError:
            return JSONResponse(status_code=503, content={"error": "事件绑定暂时不可用"})

    @router.post("/api/event-bindings")
    def create_event_binding(payload: EventBindingRequest):
        try:
            document, error = parse_request(payload)
            if error:
                return error
            result = bindings.insert_one(document)
            return _binding_response({**document, "_id": result.inserted_id})
        except DuplicateKeyError:
            return JSONResponse(status_code=409, content={"error": "该 Event 已经绑定 Workflow"})
        except PyMongoError:
            return JSONResponse(status_code=503, content={"error": "事件绑定保存失败"})

    @router.put("/api/event-bindings/{binding_id}")
    def update_event_binding(binding_id: str, payload: EventBindingRequest):
        try:
            binding_object_id = ObjectId(binding_id)
        except (InvalidId, TypeError):
            return JSONResponse(status_code=400, content={"error": "绑定 id 无效"})
        try:
            document, error = parse_request(payload)
            if error:
                return error
            updated = bindings.find_one_and_update(
                {"_id": binding_object_id},
                {"$set": document},
                return_document=ReturnDocument.AFTER,
            )
            if updated is None:
                return JSONResponse(status_code=404, content={"error": "事件绑定不存在"})
            return _binding_response(updated)
        except DuplicateKeyError:
            return JSONResponse(status_code=409, content={"error": "该 Event 已经绑定 Workflow"})
        except PyMongoError:
            return JSONResponse(status_code=503, content={"error": "事件绑定保存失败"})

    @router.delete("/api/event-bindings/{binding_id}")
    def delete_event_binding(binding_id: str):
        try:
            binding_object_id = ObjectId(binding_id)
        except (InvalidId, TypeError):
            return JSONResponse(status_code=400, content={"error": "绑定 id 无效"})
        try:
            result = bindings.delete_one({"_id": binding_object_id})
        except PyMongoError:
            return JSONResponse(status_code=503, content={"error": "事件绑定删除失败"})
        if result.deleted_count == 0:
            return JSONResponse(status_code=404, content={"error": "事件绑定不存在"})
        return {"deleted": True}

    return router
