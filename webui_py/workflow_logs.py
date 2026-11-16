from datetime import datetime, timezone

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from pymongo import DESCENDING
from pymongo.collection import Collection
from pymongo.errors import PyMongoError


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
            document["id"] = str(document.pop("_id", ""))
            items.append(document)
        return {"fetched_at": datetime.now(timezone.utc), "items": items}

    return router
