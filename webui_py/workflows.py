import json
import logging
from datetime import datetime, timezone
from typing import Any

import redis
from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from pymongo.collection import Collection
from pymongo.errors import PyMongoError

MAX_WORKFLOW_NODES = 200
MAX_WORKFLOW_CONNECTIONS = 1000

logger = logging.getLogger("aagent.webui")


class WorkflowRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    version: int = Field(ge=1)
    nodes: list[dict[str, Any]] = Field(min_length=1, max_length=MAX_WORKFLOW_NODES)
    connections: list[dict[str, Any]] = Field(default_factory=list, max_length=MAX_WORKFLOW_CONNECTIONS)


def workflow_response(document: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(document["_id"]),
        "key": document.get("key", ""),
        "name": document.get("name", ""),
        "version": document.get("version", 1),
        "nodes": document.get("nodes", []),
        "connections": document.get("connections", []),
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

    @router.put("/api/workflows/{workflow_key}")
    def upsert_workflow(workflow_key: str, payload: WorkflowRequest):
        key = workflow_key.strip()
        if not key or len(key) > 120 or not all(character.isalnum() or character in {"-", "_"} for character in key):
            return JSONResponse(status_code=400, content={"error": "Workflow key 只能包含字母、数字、连字符和下划线"})
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
            "input", "router", "construct_message", "construct_content", "construct_list",
            "foreach", "llm", "tool", "tool_call",
        }
        if any(node.get("type") not in valid_node_types for node in payload.nodes):
            return JSONResponse(status_code=400, content={"error": "Workflow 包含不支持的节点类型"})

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
                {"key": key},
                {"$set": values, "$setOnInsert": {"key": key, "created_at": now}},
                upsert=True,
                return_document=True,
            )
        except PyMongoError:
            return JSONResponse(status_code=503, content={"error": "暂时无法保存 Workflow"})
        return workflow_response(document)

    return router