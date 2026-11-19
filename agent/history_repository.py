"""Read archived events from the legacy history collection."""

import os

from pymongo import DESCENDING, MongoClient

MONGO_HOST = os.getenv("MONGO_HOST", "mongodb")
MONGO_PORT = int(os.getenv("MONGO_PORT", "27017"))
MONGO_USER = os.getenv("MONGO_USER")
MONGO_PASS = os.getenv("MONGO_PASS")
MONGO_DATABASE = os.getenv("MONGO_DATABASE", "agent")
MONGO_HISTORY_COLLECTION = os.getenv("MONGO_HISTORY_COLLECTION", "event_history")

_client = None
_collection = None


def get_history_collection():
    global _client, _collection
    if _collection is None:
        options = {
            "host": MONGO_HOST,
            "port": MONGO_PORT,
            "serverSelectionTimeoutMS": 5000,
            "tz_aware": True,
        }
        if MONGO_USER:
            options.update(username=MONGO_USER, password=MONGO_PASS, authSource="admin")
        _client = MongoClient(**options)
        _collection = _client[MONGO_DATABASE][MONGO_HISTORY_COLLECTION]
    return _collection


def get_recent_history(
    limit: int = 10,
    query: dict | None = None,
    event_types: list[str] | None = None,
) -> list[dict]:
    if limit <= 0:
        return []
    history_query = dict(query or {})
    if event_types is not None:
        history_query["event_type"] = {"$in": event_types}
    cursor = (
        get_history_collection()
        .find(history_query, {"_id": 0})
        .sort("_id", DESCENDING)
        .limit(limit)
    )
    return list(cursor)
