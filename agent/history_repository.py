import os
from datetime import datetime, timezone

from pymongo import ASCENDING, DESCENDING, MongoClient

MONGO_HOST = os.getenv("MONGO_HOST", "mongodb")
MONGO_PORT = int(os.getenv("MONGO_PORT", "27017"))
MONGO_USER = os.getenv("MONGO_USER")
MONGO_PASS = os.getenv("MONGO_PASS")
MONGO_DATABASE = os.getenv("MONGO_DATABASE", "agent")
MONGO_HISTORY_COLLECTION = os.getenv(
    "MONGO_HISTORY_COLLECTION",
    "event_history",
)

_client = None
_collection = None


def get_history_collection():
    global _client, _collection
    if _collection is None:
        client_options = {
            "host": MONGO_HOST,
            "port": MONGO_PORT,
            "serverSelectionTimeoutMS": 5000,
            "tz_aware": True,
        }
        if MONGO_USER:
            client_options.update(
                username=MONGO_USER,
                password=MONGO_PASS,
                authSource="admin",
            )

        _client = MongoClient(**client_options)
        _collection = _client[MONGO_DATABASE][MONGO_HISTORY_COLLECTION]
        _collection.create_index(
            [("created_at", DESCENDING)],
            name="created_at_desc",
        )
        _collection.create_index(
            [("event_type", ASCENDING), ("created_at", DESCENDING)],
            name="event_type_created_at",
        )
        _collection.create_index(
            [("args.id", ASCENDING)],
            name="tool_call_id",
            sparse=True,
        )
    return _collection


def record_history(e: dict):
    document = {
        **e,
        "created_at": datetime.now(timezone.utc),
    }
    return get_history_collection().insert_one(document).inserted_id

def get_recent_history(limit: int = 10, event_type: str | None = None) -> list[dict]:
    if limit <= 0:
        return []

    query = {}
    if event_type is not None:
        query["event_type"] = event_type

    cursor = (
        get_history_collection()
        .find(query, {"_id": 0})
        .sort("created_at", DESCENDING)
        .limit(limit)
    )
    return list(cursor)