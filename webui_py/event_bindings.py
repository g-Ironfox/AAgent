import json
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

from file_store import FileMissingError, FileStore

EVENT_TYPE_PATTERN = re.compile(r"^[a-z][a-z0-9_.-]*$")
MAX_EVENT_TYPE_LENGTH = 80


class EventBindingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_type: str = Field(min_length=1, max_length=MAX_EVENT_TYPE_LENGTH)
    workflow_file_id: str = Field(min_length=1, max_length=200)
    enabled: bool = True


def _binding_response(document: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(document["_id"]),
        "event_type": document.get("event_type", ""),
        "workflow_file_id": document.get("workflow_file_id", ""),
        "workflow_file_name": document.get("workflow_file_name", ""),
        "workflow_name": document.get("workflow_name", ""),
        "enabled": document.get("enabled", True),
        "created_at": document.get("created_at"),
        "updated_at": document.get("updated_at"),
    }


def _workflow_file_option(file: dict[str, Any]) -> dict[str, Any]:
    try:
        workflow = json.loads(file["content"])
    except (ValueError, TypeError) as error:
        raise ValueError("文件内容必须是 Workflow JSON") from error
    if not isinstance(workflow, dict) or workflow.get("schema_version") != "2.0":
        raise ValueError("请选择 schema_version 为 2.0 的 Workflow 文件")
    if not isinstance(workflow.get("name"), str) or any(
        not isinstance(workflow.get(field), list)
        for field in ("nodes", "connections", "input_ports", "output_ports")
    ):
        raise ValueError("Workflow 文件缺少名称、节点、连接或端口声明")
    for field in ("input_ports", "output_ports"):
        if any(
            not isinstance(port, dict)
            or not isinstance(port.get("name"), str)
            or not isinstance(port.get("type"), str)
            for port in workflow[field]
        ):
            raise ValueError("Workflow 文件端口声明无效")
    return {
        "file_id": file["file_id"],
        "name": file["name"],
        "workflow_name": workflow["name"],
        "input_ports": workflow["input_ports"],
        "output_ports": workflow["output_ports"],
    }


def create_event_bindings_router(bindings: Collection, store: FileStore) -> APIRouter:
    router = APIRouter()

    @router.get("/api/event-bindings/workflow-options")
    def list_workflow_options():
        items = []
        for file in store.list_files():
            try:
                items.append(_workflow_file_option(store.get_file(file["file_id"])))
            except (FileMissingError, ValueError):
                continue
        return {"items": sorted(items, key=lambda item: (item["name"], item["file_id"]))}

    def parse_request(payload: EventBindingRequest) -> tuple[dict[str, Any] | None, JSONResponse | None]:
        event_type = payload.event_type.strip().lower()
        if not EVENT_TYPE_PATTERN.fullmatch(event_type):
            return None, JSONResponse(status_code=400, content={"error": "Event 类型只能包含小写字母、数字、点、下划线和短横线"})
        try:
            file = store.get_file(payload.workflow_file_id)
            _workflow_file_option(file)
        except FileMissingError:
            return None, JSONResponse(status_code=404, content={"error": "Workspace 文件不存在或已被删除"})
        except ValueError as error:
            return None, JSONResponse(status_code=400, content={"error": str(error)})
        return {
            "event_type": event_type,
            "workflow_file_id": file["file_id"],
            "workflow_file_name": file["name"],
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
                {"$set": document, "$unset": {"workflow_name": "", "workflow_id": ""}},
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
