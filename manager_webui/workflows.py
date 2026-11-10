import json
from datetime import datetime, timezone
from typing import Any, Literal

import redis
from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from pymongo import DESCENDING
from pymongo.collection import Collection
from pymongo.errors import DuplicateKeyError, PyMongoError

from workflow_node_remap import remap_workflow_node_names
from workflow_validator import WorkflowValidationError, validate_workflow

MAX_WORKFLOW_NODES = 200
MAX_WORKFLOW_CONNECTIONS = 1000
MAX_WORKFLOW_METADATA_PORTS = 50
MAX_WORKFLOW_NODE_REFERENCES = 50
MAX_REMOTE_TOOL_REFERENCES = 100
MAX_WORKFLOW_DESCRIPTION_LENGTH = 2000
WORKFLOW_SCHEMA_VERSION = "2.0"


def node_arguments(node: dict[str, Any]) -> dict[str, Any]:
    arguments = node.get("arguments")
    return arguments if isinstance(arguments, dict) else {}


def workflow_port_values(ports: list[Any]) -> list[dict[str, Any]]:
    return [port.model_dump() if isinstance(port, BaseModel) else dict(port) for port in ports]


class WorkflowPortMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=80)
    type: Literal["content", "message", "event", "map-content", "list-content", "list-message", "list-event"]


class WorkflowRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=MAX_WORKFLOW_DESCRIPTION_LENGTH)
    schema_version: Literal["2.0"]
    metadata: dict[str, Any] = Field(default_factory=dict)
    input_ports: list[WorkflowPortMetadata] = Field(max_length=MAX_WORKFLOW_METADATA_PORTS)
    output_ports: list[WorkflowPortMetadata] = Field(max_length=MAX_WORKFLOW_METADATA_PORTS)
    nodes: list[dict[str, Any]] = Field(min_length=1, max_length=MAX_WORKFLOW_NODES)
    connections: list[dict[str, Any]] = Field(default_factory=list, max_length=MAX_WORKFLOW_CONNECTIONS)
    workflow_nodes: list[dict[str, Any]] = Field(default_factory=list, max_length=MAX_WORKFLOW_NODE_REFERENCES)
    remote_tools: list[dict[str, Any]] = Field(default_factory=list, max_length=MAX_REMOTE_TOOL_REFERENCES)


class WorkflowCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)


class WorkflowRenameRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)


class WorkflowNodeReference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    input_ports: list[WorkflowPortMetadata] | None = None
    output_ports: list[WorkflowPortMetadata] | None = None
    previous_name: str | None = Field(default=None, max_length=120)


class WorkflowMetadataPatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    workflow_nodes: list[WorkflowNodeReference] | None = None


class RemoteToolReference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=128)
    input_ports: list[WorkflowPortMetadata] = Field(default_factory=list, max_length=MAX_WORKFLOW_METADATA_PORTS)
    output_ports: list[WorkflowPortMetadata] = Field(default_factory=list, max_length=MAX_WORKFLOW_METADATA_PORTS)


def workflow_response(document: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": document.get("name", ""),
        "description": document.get("description", ""),
        "schema_version": document.get("schema_version"),
        "metadata": document.get("metadata", {}),
        "nodes": document.get("nodes", []),
        "connections": document.get("connections", []),
        "input_ports": document.get("input_ports", []),
        "output_ports": document.get("output_ports", []),
        "workflow_nodes": document.get("workflow_nodes", []),
        "remote_tools": document.get("remote_tools", []),
        "created_at": document.get("created_at"),
        "updated_at": document.get("updated_at"),
    }


def create_workflows_router(
    redis_client: redis.Redis,
    tools_key: str,
    model_configs: Collection,
    workflows: Collection,
) -> APIRouter:
    router = APIRouter()

    @router.get("/api/workflows")
    def list_workflows():
        try:
            items = workflows.find(
                {},
                {"name": 1, "description": 1, "schema_version": 1, "metadata": 1, "nodes": 1, "connections": 1, "input_ports": 1, "output_ports": 1, "workflow_nodes": 1, "remote_tools": 1, "created_at": 1, "updated_at": 1},
            ).sort("updated_at", DESCENDING)
            return {
                "items": [
                    {
                        "name": item.get("name", ""),
                        "description": item.get("description", ""),
                        "schema_version": item.get("schema_version"),
                        "metadata": item.get("metadata", {}),
                        "node_count": len(item.get("nodes", [])),
                        "connection_count": len(item.get("connections", [])),
                        "input_ports": item.get("input_ports", []),
                        "output_ports": item.get("output_ports", []),
                        "workflow_nodes": item.get("workflow_nodes", []),
                        "remote_tools": item.get("remote_tools", []),
                        "created_at": item.get("created_at"),
                        "updated_at": item.get("updated_at"),
                    }
                    for item in items
                ]
            }
        except PyMongoError:
            return JSONResponse(status_code=503, content={"error": "Workflow 列表暂时不可用"})

    @router.get("/api/workflow/{name}")
    def get_workflow(name: str):
        try:
            document = workflows.find_one({"name": name})
        except PyMongoError:
            return JSONResponse(status_code=503, content={"error": "Workflow 暂时不可用"})
        if document is None:
            return JSONResponse(status_code=404, content={"error": "Workflow 不存在或已被删除"})
        return workflow_response(document)

    @router.post("/api/workflow/{name}", status_code=201)
    def create_workflow(name: str, payload: WorkflowRequest):
        return save_workflow(name, payload, overwrite=False)

    @router.put("/api/workflow/{name}")
    def overwrite_workflow(name: str, payload: WorkflowRequest):
        return save_workflow(name, payload, overwrite=True)

    def save_workflow(name: str, payload: WorkflowRequest, overwrite: bool):
        if not name:
            return JSONResponse(status_code=400, content={"error": "Workflow 名称不能为空"})
        if payload.name != name:
            return JSONResponse(status_code=400, content={"error": "请求路径名称必须与 Workflow JSON 的 name 一致"})
        try:
            existing = workflows.find_one({"name": name})
            if overwrite and existing is None:
                return JSONResponse(status_code=404, content={"error": "Workflow 不存在或已被删除"})
            if not overwrite and existing is not None:
                return JSONResponse(status_code=409, content={"error": "Workflow 名称已存在"})
            input_ports = [port.model_dump() | {"name": port.name.strip()} for port in payload.input_ports]
            output_ports = [port.model_dump() | {"name": port.name.strip()} for port in payload.output_ports]
            references = payload.workflow_nodes
            reference_names = [item.get("name", "") for item in references]
            if any(not reference_name for reference_name in reference_names) or len(reference_names) != len(set(reference_names)):
                return JSONResponse(status_code=400, content={"error": "Workflow 依赖名称不能为空或重复"})
            if name in reference_names:
                return JSONResponse(status_code=400, content={"error": "Workflow 不能引入自身"})
            canonical_references = []
            for reference in references:
                input_contract = workflow_port_values(reference.get("input_ports", []))
                output_contract = workflow_port_values(reference.get("output_ports", []))
                canonical_references.append({"name": reference["name"], "input_ports": input_contract, "output_ports": output_contract})
            values = payload.model_dump()
            values.update({"name": name, "input_ports": input_ports, "output_ports": output_ports, "workflow_nodes": canonical_references})
            try:
                validate_workflow(values)
            except WorkflowValidationError as error:
                return JSONResponse(status_code=400, content={"error": str(error)})
            local_tools = [node for node in values["nodes"] if node.get("type") == "local_tool"]
            if local_tools:
                registered = {value.decode() if isinstance(value, bytes) else value for value in redis_client.hkeys(tools_key)}
                if any(node_arguments(node).get("tool") not in registered for node in local_tools):
                    return JSONResponse(status_code=400, content={"error": "Tool 节点引用了未注册的工具"})
            model_nodes = [node for node in values["nodes"] if node.get("type") == "llm"]
            model_ids = [ObjectId(node_arguments(node).get("model", "")) for node in model_nodes]
            available = {item["_id"] for item in model_configs.find({"_id": {"$in": model_ids}, "enabled": True}, {"_id": 1})} if model_ids else set()
            if any(model_id not in available for model_id in model_ids):
                return JSONResponse(status_code=400, content={"error": "LLM 节点引用了不存在或已停用的模型配置"})
        except (InvalidId, TypeError, ValueError, KeyError) as error:
            return JSONResponse(status_code=400, content={"error": f"Workflow 契约无效: {error}"})
        except redis.RedisError:
            return JSONResponse(status_code=503, content={"error": "暂时无法校验 Tool 注册表"})
        except PyMongoError:
            return JSONResponse(status_code=503, content={"error": "暂时无法校验或保存 Workflow"})

        now = datetime.now(timezone.utc)
        values["description"] = values["description"].strip()
        values["updated_at"] = now
        try:
            if overwrite:
                values["created_at"] = existing.get("created_at", now)
                workflows.replace_one({"_id": existing["_id"]}, values)
                document = workflows.find_one({"_id": existing["_id"]})
            else:
                values["created_at"] = now
                result = workflows.insert_one(values)
                values["_id"] = result.inserted_id
                document = values
        except DuplicateKeyError:
            return JSONResponse(status_code=409, content={"error": "Workflow 名称已存在"})
        except PyMongoError:
            return JSONResponse(status_code=503, content={"error": "暂时无法保存 Workflow"})
        return workflow_response(document)

    @router.patch("/api/workflow/{name}/metadata")
    def update_workflow_metadata(name: str, payload: WorkflowMetadataPatchRequest):
        # 改名和删除只作用于目标 Workflow，不级联改写其他引用处；全量同步代价大且没有功能收益。
        next_name = payload.name
        try:
            existing = workflows.find_one({"name": name})
            if existing is None:
                return JSONResponse(status_code=404, content={"error": "Workflow 不存在或已被删除"})
            if workflows.find_one({"name": next_name, "_id": {"$ne": existing["_id"]}}):
                return JSONResponse(status_code=409, content={"error": "Workflow 名称已存在"})
            updates = {"name": next_name, "updated_at": datetime.now(timezone.utc)}
            if payload.workflow_nodes is not None:
                references = [reference.model_dump(exclude_none=True) for reference in payload.workflow_nodes]
                names = [reference["name"] for reference in references]
                if len(names) != len(set(names)):
                    return JSONResponse(status_code=400, content={"error": "Workflow 依赖名称重复"})
                existing_references = {
                    reference["name"]: reference
                    for reference in existing.get("workflow_nodes", [])
                    if isinstance(reference, dict) and isinstance(reference.get("name"), str)
                }
                remapped_nodes = remap_workflow_node_names(existing.get("nodes", []), references)
                canonical_references = []
                for reference in references:
                    previous_name = reference.get("previous_name", reference["name"])
                    previous = existing_references.get(previous_name, {})
                    canonical_references.append({
                        "name": reference["name"],
                        "input_ports": workflow_port_values(reference["input_ports"])
                        if "input_ports" in reference else previous.get("input_ports", []),
                        "output_ports": workflow_port_values(reference["output_ports"])
                        if "output_ports" in reference else previous.get("output_ports", []),
                    })
                updates.update({
                    "workflow_nodes": canonical_references,
                    "nodes": remapped_nodes,
                })
            candidate = {**existing, **updates}
            try:
                validate_workflow(candidate)
            except WorkflowValidationError as error:
                return JSONResponse(status_code=400, content={"error": str(error)})
            workflows.update_one({"_id": existing["_id"]}, {"$set": updates})
            document = workflows.find_one({"_id": existing["_id"]})
        except PyMongoError:
            return JSONResponse(status_code=503, content={"error": "暂时无法更新 Workflow 元数据"})
        return workflow_response(document)

    @router.delete("/api/workflow/{name}")
    def delete_workflow(name: str):
        # 删除只移除目标 Workflow，不扫描或修改其他 Workflow 中的引用。
        try:
            result = workflows.delete_one({"name": name})
        except PyMongoError:
            return JSONResponse(status_code=503, content={"error": "暂时无法删除 Workflow"})
        if result.deleted_count == 0:
            return JSONResponse(status_code=404, content={"error": "Workflow 不存在或已被删除"})
        return {"deleted": True, "name": name}

    return router
