import logging
from datetime import datetime, timezone
from typing import Any

from pymongo import ASCENDING, DESCENDING
from pymongo.asynchronous.collection import AsyncCollection
from pymongo.errors import PyMongoError


logger = logging.getLogger("aagent.tool_server.task_log")


class TaskLogRepository:
    def __init__(self, collection: AsyncCollection):
        self.collection = collection

    async def create_indexes(self) -> None:
        await self.collection.create_index(
            [("task_id", ASCENDING), ("logged_at", ASCENDING)],
            name="task_id_logged_at",
        )
        await self.collection.create_index(
            [("logged_at", DESCENDING)],
            name="logged_at_desc",
        )

    async def record(self, event_type: str, task: dict[str, Any]) -> None:
        try:
            await self.collection.insert_one(
                {
                    "task_id": task["task_id"],
                    "tool": task["tool"],
                    "provider_id": task.get("provider_id"),
                    "status": task["status"],
                    "event_type": event_type,
                    "logged_at": datetime.now(timezone.utc),
                    "task": task,
                }
            )
        except PyMongoError:
            logger.exception(
                "failed to persist tool task log task_id=%s event_type=%s",
                task["task_id"],
                event_type,
            )

    async def list_recent(self, limit: int = 100) -> list[dict[str, Any]]:
        cursor = await self.collection.aggregate(
            [
                {"$sort": {"logged_at": -1}},
                {
                    "$group": {
                        "_id": "$task_id",
                        "task": {"$first": "$task"},
                        "logged_at": {"$first": "$logged_at"},
                    }
                },
                {"$sort": {"logged_at": -1}},
                {"$limit": limit},
                {"$replaceWith": "$task"},
            ]
        )
        return [task async for task in cursor]

    async def get_latest(self, task_id: str) -> dict[str, Any] | None:
        document = await self.collection.find_one(
            {"task_id": task_id},
            {"_id": 0, "task": 1},
            sort=[("logged_at", DESCENDING)],
        )
        return document["task"] if document else None