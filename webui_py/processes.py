"""Queue workflow process creation requests for the Agent runtime."""

import json
import logging
import os
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from redis.exceptions import RedisError

from file_store import FileMissingError

logger = logging.getLogger(__name__)
EXTERNAL_EVENTS = os.getenv("ExternalEvents", "external_events")


class CreateProcessRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workflow_file_id: str = Field(min_length=1, max_length=200)
    terminal_id: str = Field(min_length=1, max_length=256)
    inputs: dict[str, Any] = Field(default_factory=dict)


def _workflow_option(file: dict[str, Any]) -> dict[str, Any]:
    try:
        document = json.loads(file["content"])
    except (ValueError, TypeError) as error:
        raise ValueError("workflow file content must be valid JSON") from error
    if not isinstance(document, dict) or document.get("schema_version") != "2.0":
        raise ValueError("workflow file must use schema_version 2.0")
    if any(
        not isinstance(document.get(field), list)
        for field in ("nodes", "connections", "input_ports", "output_ports")
    ):
        raise ValueError("workflow file is missing its nodes, connections, or ports")
    for field in ("input_ports", "output_ports"):
        if any(
            not isinstance(port, dict)
            or not isinstance(port.get("name"), str)
            or not isinstance(port.get("type"), str)
            for port in document[field]
        ):
            raise ValueError("workflow port declaration is invalid")
    return {
        "file_id": file["file_id"],
        "name": file["name"],
        "workflow_name": file["name"],
        "input_ports": document["input_ports"],
        "output_ports": document["output_ports"],
    }


def create_processes_router(redis_client, store) -> APIRouter:
    router = APIRouter()

    @router.get("/api/processes/workflow-options")
    def list_workflow_options():
        items = []
        for file in store.list_files():
            try:
                items.append(_workflow_option(store.get_file(file["file_id"])))
            except (FileMissingError, ValueError):
                continue
        return {"items": sorted(items, key=lambda item: (item["name"], item["file_id"]))}

    @router.post("/api/processes", status_code=202)
    def create_process(request: CreateProcessRequest):
        try:
            file = store.get_file(request.workflow_file_id)
        except FileMissingError:
            return JSONResponse(status_code=404, content={"error": "workflow file not found"})

        try:
            document = json.loads(file["content"])
            if not isinstance(document, dict):
                raise ValueError("workflow file must contain a JSON object")
            encoded_event = json.dumps({
                "type": "create_process",
                "workflow_content": file["content"],
                "workflow_file_id": request.workflow_file_id,
                "workflow_name": file["name"],
                "inputs": request.inputs,
                "terminal_id": request.terminal_id,
            }, ensure_ascii=False, allow_nan=False)
        except (ValueError, TypeError) as error:
            return JSONResponse(status_code=400, content={"error": str(error)})

        try:
            redis_client.lpush(EXTERNAL_EVENTS, encoded_event)
        except RedisError:
            logger.exception("failed to queue process creation")
            return JSONResponse(status_code=503, content={"error": "process creation queue unavailable"})

        return {
            "status": "queued",
            "terminal_id": request.terminal_id,
            "workflow_name": file["name"],
        }

    return router
