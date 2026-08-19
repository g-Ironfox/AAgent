import json
from typing import Any

import redis
from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from pymongo.database import Database
from pymongo.collection import Collection
from pymongo.errors import PyMongoError

from common import limit_error
from events import event_snapshot

MAX_SUBAGENT_DOCUMENTS = 100


class SubagentSpec(BaseModel):
    id: str
    name: str
    description: str
    queue: str
    history_collection: str
    worker_status_key: str


class SubagentSettingsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_ids: list[str] = Field(default_factory=list, max_length=MAX_SUBAGENT_DOCUMENTS)


def create_subagents_router(
    redis_client: redis.Redis,
    database: Database,
    documents: Collection,
    subagents: dict[str, SubagentSpec],
) -> APIRouter:
    router = APIRouter(prefix="/api/subagents")

    def subagent_spec(agent_id: str) -> SubagentSpec | JSONResponse:
        spec = subagents.get(agent_id)
        if spec is None:
            return JSONResponse(status_code=404, content={"error": "子 Agent 不存在"})
        return spec

    def subagent_settings_key(agent_id: str) -> str:
        return f"subagent:{agent_id}:settings"

    def selected_document_ids(agent_id: str) -> list[str]:
        raw = redis_client.get(subagent_settings_key(agent_id))
        if not raw:
            return []
        try:
            value = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            return []
        document_ids = value.get("document_ids", []) if isinstance(value, dict) else []
        return [item for item in document_ids if isinstance(item, str)]

    @router.get("")
    def list_subagents():
        items = []
        for spec in subagents.values():
            snapshot = event_snapshot(
                redis_client,
                1,
                spec.queue,
                database[spec.history_collection],
                spec.worker_status_key,
            )
            items.append(
                {
                    "id": spec.id,
                    "name": spec.name,
                    "description": spec.description,
                    "queue": spec.queue,
                    "history_collection": spec.history_collection,
                    "worker_status_key": spec.worker_status_key,
                    "summary": snapshot["summary"],
                    "worker": snapshot["worker"],
                    "sources": snapshot["sources"],
                }
            )
        return {"items": items}

    @router.get("/{agent_id}/events")
    def subagent_events(agent_id: str, limit: int = Query(150)):
        error = limit_error(limit)
        if error:
            return error
        spec = subagent_spec(agent_id)
        if isinstance(spec, JSONResponse):
            return spec
        snapshot = event_snapshot(
            redis_client,
            limit,
            spec.queue,
            database[spec.history_collection],
            spec.worker_status_key,
        )
        snapshot["agent"] = {"id": spec.id, "name": spec.name, "description": spec.description}
        return snapshot

    @router.get("/{agent_id}/settings")
    def get_subagent_settings(agent_id: str):
        spec = subagent_spec(agent_id)
        if isinstance(spec, JSONResponse):
            return spec
        try:
            return {"document_ids": selected_document_ids(agent_id)}
        except redis.RedisError as error:
            return JSONResponse(status_code=503, content={"error": str(error)})

    @router.put("/{agent_id}/settings")
    def update_subagent_settings(agent_id: str, payload: SubagentSettingsRequest):
        spec = subagent_spec(agent_id)
        if isinstance(spec, JSONResponse):
            return spec
        unique_ids = list(dict.fromkeys(payload.document_ids))
        try:
            object_ids = [ObjectId(document_id) for document_id in unique_ids]
        except InvalidId:
            return JSONResponse(status_code=400, content={"error": "文档 ID 无效"})
        try:
            existing_ids = {str(item["_id"]) for item in documents.find({"_id": {"$in": object_ids}}, {"_id": 1})}
            missing_ids = [document_id for document_id in unique_ids if document_id not in existing_ids]
            if missing_ids:
                return JSONResponse(status_code=400, content={"error": "包含不存在的文档", "document_ids": missing_ids})
            settings = {"document_ids": unique_ids}
            redis_client.set(subagent_settings_key(agent_id), json.dumps(settings, ensure_ascii=False))
            return settings
        except (redis.RedisError, PyMongoError) as error:
            return JSONResponse(status_code=503, content={"error": str(error)})

    return router