import json
import logging
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

MAX_WORKFLOW_NODES = 200
MAX_WORKFLOW_CONNECTIONS = 1000
MAX_WORKFLOW_METADATA_PORTS = 50

logger = logging.getLogger("aagent.webui")


class WorkflowRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    version: int = Field(ge=1)
    nodes: list[dict[str, Any]] = Field(min_length=1, max_length=MAX_WORKFLOW_NODES)
    connections: list[dict[str, Any]] = Field(default_factory=list, max_length=MAX_WORKFLOW_CONNECTIONS)


class WorkflowCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)


class WorkflowRenameRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)


class WorkflowPortMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=80)
    type: Literal["content", "message", "list-content", "list-message"]


class WorkflowMetadataRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input_ports: list[WorkflowPortMetadata] = Field(default_factory=list, max_length=MAX_WORKFLOW_METADATA_PORTS)
    output_ports: list[WorkflowPortMetadata] = Field(default_factory=list, max_length=MAX_WORKFLOW_METADATA_PORTS)


def duplicate_port_name(ports: list[WorkflowPortMetadata]) -> bool:
    names = [port.name.strip() for port in ports]
    return any(not name for name in names) or len(names) != len(set(names))


def synchronize_metadata_ports(
    nodes: list[dict[str, Any]],
    connections: list[dict[str, Any]],
    input_ports: list[dict[str, Any]],
    output_ports: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    input_node_ids = {node.get("id") for node in nodes if node.get("type") == "input"}
    output_node_ids = {node.get("id") for node in nodes if node.get("type") == "output"}
    input_node_ports = [{**port, "id": f"workflow:{port['name']}"} for port in input_ports]
    output_node_ports = [{**port, "id": f"workflow:{port['name']}"} for port in output_ports]
    input_types = {port["id"]: port["type"] for port in input_node_ports}
    output_types = {port["id"]: port["type"] for port in output_node_ports}
    synchronized_nodes = [
        {
            **node,
            **(
                {"workflowPorts": input_node_ports}
                if node.get("type") == "input"
                else {"workflowPorts": output_node_ports}
                if node.get("type") == "output"
                else {}
            ),
        }
        for node in nodes
    ]
    synchronized_connections = []
    for connection in connections:
        connection_type = connection.get("type")
        if connection_type == "control":
            synchronized_connections.append(connection)
            continue
        if connection.get("fromId") in input_node_ids and input_types.get(connection.get("fromPortId")) != connection_type:
            continue
        if connection.get("toId") in output_node_ids and output_types.get(connection.get("toPortId")) != connection_type:
            continue
        synchronized_connections.append(connection)
    return synchronized_nodes, synchronized_connections


def workflow_response(document: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(document["_id"]),
        "name": document.get("name", ""),
        "version": document.get("version", 1),
        "nodes": document.get("nodes", []),
        "connections": document.get("connections", []),
        "input_ports": document.get("input_ports", []),
        "output_ports": document.get("output_ports", []),
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
                {"name": 1, "version": 1, "nodes": 1, "connections": 1, "input_ports": 1, "output_ports": 1, "created_at": 1, "updated_at": 1},
            ).sort("updated_at", DESCENDING)
            return {
                "items": [
                    {
                        "id": str(item["_id"]),
                        "name": item.get("name", ""),
                        "version": item.get("version", 1),
                        "node_count": len(item.get("nodes", [])),
                        "connection_count": len(item.get("connections", [])),
                        "input_ports": item.get("input_ports", []),
                        "output_ports": item.get("output_ports", []),
                        "created_at": item.get("created_at"),
                        "updated_at": item.get("updated_at"),
                    }
                    for item in items
                ]
            }
        except PyMongoError:
            return JSONResponse(status_code=503, content={"error": "Workflow 列表暂时不可用"})

    @router.post("/api/workflows", status_code=201)
    def create_workflow(payload: WorkflowCreateRequest):
        name = payload.name.strip()
        if not name:
            return JSONResponse(status_code=400, content={"error": "Workflow 名称不能为空"})
        now = datetime.now(timezone.utc)
        document = {
            "name": name,
            "version": 1,
            "nodes": [
                {"id": "input", "type": "input", "name": "Input", "x": 120, "y": 238},
                {"id": "output", "type": "output", "name": "Output", "x": 520, "y": 238},
            ],
            "connections": [
                {
                    "id": "control-input-output",
                    "fromId": "input",
                    "fromPortId": "control-out",
                    "toId": "output",
                    "toPortId": "control-in",
                    "type": "control",
                },
                {
                    "id": "content-input-output",
                    "fromId": "input",
                    "fromPortId": "content-out",
                    "toId": "output",
                    "toPortId": "content-in",
                    "type": "content",
                },
            ],
            "input_ports": [],
            "output_ports": [],
            "created_at": now,
            "updated_at": now,
        }
        try:
            result = workflows.insert_one(document)
        except PyMongoError:
            return JSONResponse(status_code=503, content={"error": "暂时无法创建 Workflow"})
        document["_id"] = result.inserted_id
        return workflow_response(document)

    @router.get("/api/tools")
    def list_tools():
        try:
            schemas = redis_client.hgetall(tools_key)
        except redis.RedisError:
            return JSONResponse(status_code=503, content={"error": "Tool 注册表暂时不可用"})

        items = []
        for tool_name, raw_schema in schemas.items():
            try:
                schema = json.loads(raw_schema)
            except (TypeError, ValueError):
                logger.warning("ignored invalid tool schema name=%s", tool_name)
                continue
            function_schema = schema.get("function", {}) if isinstance(schema, dict) else {}
            if function_schema.get("name") != tool_name:
                logger.warning("ignored mismatched tool schema name=%s", tool_name)
                continue
            items.append(
                {
                    "name": tool_name,
                    "description": function_schema.get("description", ""),
                    "parameters": function_schema.get("parameters", {}),
                }
            )
        items.sort(key=lambda item: item["name"])
        return {"items": items}

    def workflow_object_id(workflow_id: str) -> ObjectId | JSONResponse:
        try:
            return ObjectId(workflow_id)
        except (InvalidId, TypeError):
            return JSONResponse(status_code=400, content={"error": "Workflow id 无效"})

    @router.get("/api/workflows/{workflow_id}")
    def get_workflow(workflow_id: str):
        object_id = workflow_object_id(workflow_id)
        if isinstance(object_id, JSONResponse):
            return object_id
        try:
            document = workflows.find_one({"_id": object_id})
        except PyMongoError:
            return JSONResponse(status_code=503, content={"error": "Workflow 暂时不可用"})
        if document is None:
            return JSONResponse(status_code=404, content={"error": "Workflow 不存在或已被删除"})
        return workflow_response(document)

    @router.patch("/api/workflows/{workflow_id}")
    def rename_workflow(workflow_id: str, payload: WorkflowRenameRequest):
        name = payload.name.strip()
        if not name:
            return JSONResponse(status_code=400, content={"error": "Workflow 名称不能为空"})
        object_id = workflow_object_id(workflow_id)
        if isinstance(object_id, JSONResponse):
            return object_id
        try:
            document = workflows.find_one_and_update(
                {"_id": object_id},
                {"$set": {"name": name, "updated_at": datetime.now(timezone.utc)}},
                return_document=True,
            )
        except PyMongoError:
            return JSONResponse(status_code=503, content={"error": "暂时无法重命名 Workflow"})
        if document is None:
            return JSONResponse(status_code=404, content={"error": "Workflow 不存在或已被删除"})
        return workflow_response(document)

    @router.put("/api/workflows/{workflow_id}/metadata")
    def update_workflow_metadata(workflow_id: str, payload: WorkflowMetadataRequest):
        if duplicate_port_name(payload.input_ports):
            return JSONResponse(status_code=400, content={"error": "Input 字段名不能为空或重复"})
        if duplicate_port_name(payload.output_ports):
            return JSONResponse(status_code=400, content={"error": "Output 字段名不能为空或重复"})
        input_ports = [port.model_dump() | {"name": port.name.strip()} for port in payload.input_ports]
        output_ports = [port.model_dump() | {"name": port.name.strip()} for port in payload.output_ports]
        object_id = workflow_object_id(workflow_id)
        if isinstance(object_id, JSONResponse):
            return object_id
        try:
            existing = workflows.find_one({"_id": object_id})
            if existing is None:
                return JSONResponse(status_code=404, content={"error": "Workflow 不存在或已被删除"})
            nodes, connections = synchronize_metadata_ports(
                existing.get("nodes", []), existing.get("connections", []), input_ports, output_ports
            )
            document = workflows.find_one_and_update(
                {"_id": object_id},
                {"$set": {
                    "input_ports": input_ports,
                    "output_ports": output_ports,
                    "nodes": nodes,
                    "connections": connections,
                    "updated_at": datetime.now(timezone.utc),
                }},
                return_document=True,
            )
        except PyMongoError:
            return JSONResponse(status_code=503, content={"error": "暂时无法保存 Workflow 元数据"})
        if document is None:
            return JSONResponse(status_code=404, content={"error": "Workflow 不存在或已被删除"})
        return workflow_response(document)

    @router.delete("/api/workflows/{workflow_id}")
    def delete_workflow(workflow_id: str):
        object_id = workflow_object_id(workflow_id)
        if isinstance(object_id, JSONResponse):
            return object_id
        try:
            result = workflows.delete_one({"_id": object_id})
        except PyMongoError:
            return JSONResponse(status_code=503, content={"error": "暂时无法删除 Workflow"})
        if result.deleted_count == 0:
            return JSONResponse(status_code=404, content={"error": "Workflow 不存在或已被删除"})
        return {"deleted": True, "id": workflow_id}

    @router.put("/api/workflows/{workflow_id}")
    def update_workflow(workflow_id: str, payload: WorkflowRequest):
        object_id = workflow_object_id(workflow_id)
        if isinstance(object_id, JSONResponse):
            return object_id
        if not payload.name.strip():
            return JSONResponse(status_code=400, content={"error": "Workflow 名称不能为空"})

        node_ids = [node.get("id") for node in payload.nodes]
        if any(not isinstance(node_id, str) or not node_id for node_id in node_ids):
            return JSONResponse(status_code=400, content={"error": "每个节点都必须包含有效的 id"})
        if len(node_ids) != len(set(node_ids)):
            return JSONResponse(status_code=400, content={"error": "Workflow 中存在重复的节点 id"})
        node_id_set = set(node_ids)
        for connection in payload.connections:
            if connection.get("fromId") not in node_id_set or connection.get("toId") not in node_id_set:
                return JSONResponse(status_code=400, content={"error": "连接引用了不存在的节点"})

        valid_node_types = {
            "input", "output", "router", "construct_message", "construct_content", "construct_list",
            "foreach", "llm", "tool", "tool_call",
        }
        if any(node.get("type") not in valid_node_types for node in payload.nodes):
            return JSONResponse(status_code=400, content={"error": "Workflow 包含不支持的节点类型"})
        if not any(node.get("type") == "output" for node in payload.nodes):
            return JSONResponse(status_code=400, content={"error": "Workflow 必须至少包含一个 Output 节点"})

        tool_nodes = [node for node in payload.nodes if node.get("type") == "tool"]
        if tool_nodes:
            try:
                registered_tool_names = set(redis_client.hkeys(tools_key))
            except redis.RedisError:
                return JSONResponse(status_code=503, content={"error": "暂时无法校验 Tool 注册表"})
            if any(node.get("tool") not in registered_tool_names for node in tool_nodes):
                return JSONResponse(status_code=400, content={"error": "Tool 节点引用了未注册的工具"})
            try:
                schemas = redis_client.hmget(tools_key, [node.get("tool") for node in tool_nodes])
                tool_properties = {
                    node.get("tool"): set(json.loads(raw).get("function", {}).get("parameters", {}).get("properties", {}))
                    for node, raw in zip(tool_nodes, schemas)
                    if raw
                }
            except (redis.RedisError, TypeError, ValueError):
                return JSONResponse(status_code=503, content={"error": "暂时无法读取 Tool 参数定义"})
            for node in tool_nodes:
                parameters = node.get("parameters", [])
                if not isinstance(parameters, list) or set(parameters) != tool_properties.get(node.get("tool"), set()):
                    return JSONResponse(status_code=400, content={"error": "Tool 节点参数端口与工具定义不一致"})

        llm_nodes = [node for node in payload.nodes if node.get("type") == "llm"]
        try:
            model_ids = [ObjectId(node.get("model", "")) for node in llm_nodes]
        except (InvalidId, TypeError):
            return JSONResponse(status_code=400, content={"error": "LLM 节点必须选择有效的模型配置"})
        try:
            available_model_ids = {
                item["_id"] for item in model_configs.find({"_id": {"$in": model_ids}, "enabled": True}, {"_id": 1})
            }
        except PyMongoError:
            return JSONResponse(status_code=503, content={"error": "暂时无法校验模型配置"})
        if any(model_id not in available_model_ids for model_id in model_ids):
            return JSONResponse(status_code=400, content={"error": "LLM 节点引用了不存在或已停用的模型配置"})

        now = datetime.now(timezone.utc)
        values = payload.model_dump()
        values["name"] = values["name"].strip()
        values["updated_at"] = now
        try:
            document = workflows.find_one_and_update(
                {"_id": object_id},
                {"$set": values, "$setOnInsert": {"created_at": now}},
                return_document=True,
            )
        except PyMongoError:
            return JSONResponse(status_code=503, content={"error": "暂时无法保存 Workflow"})
        return workflow_response(document)

    return router