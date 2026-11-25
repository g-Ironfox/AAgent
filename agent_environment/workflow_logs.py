from datetime import datetime, timezone

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from pymongo import DESCENDING
from pymongo.collection import Collection
from pymongo.errors import PyMongoError


_PRIVATE_PROCESS_FIELDS = {
    "process_id",
    "terminal_process_id",
    "parent_process_id",
    "root_process_id",
    "child_process_id",
    "invocation_id",
    "ancestor_invocation_ids",
    "run_id",
    "execution_id",
}


def _public_value(value):
    if isinstance(value, dict):
        return {
            key: _public_value(item)
            for key, item in value.items()
            if key not in _PRIVATE_PROCESS_FIELDS
        }
    if isinstance(value, list):
        return [_public_value(item) for item in value]
    return value


def create_workflow_logs_router(logs: Collection) -> APIRouter:
    router = APIRouter()

    @router.get("/api/workflow-logs")
    def list_workflow_logs(limit: int = Query(200, ge=1, le=500)):
        try:
            documents = list(logs.find({}).sort("_id", DESCENDING).limit(limit))
        except PyMongoError:
            return JSONResponse(status_code=503, content={"error": "workflow logs are unavailable"})

        items = []
        for document in documents:
            item = _public_value(document)
            item.pop("_id", None)
            item["id"] = str(document.get("_id", ""))
            items.append(item)
        return {"fetched_at": datetime.now(timezone.utc), "items": items}

    return router
