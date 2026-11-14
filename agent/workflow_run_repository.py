import os
from typing import Any

from pymongo import ASCENDING, DESCENDING, MongoClient

MONGO_HOST = os.getenv("MONGO_HOST", "mongodb")
MONGO_PORT = int(os.getenv("MONGO_PORT", "27017"))
MONGO_DATABASE = os.getenv("MONGO_DATABASE", "agent")
MONGO_WORKFLOW_LOG_COLLECTION = os.getenv("MONGO_WORKFLOW_LOG_COLLECTION", "workflow_logs")
MONGO_USER = os.getenv("MONGO_USER")
MONGO_PASS = os.getenv("MONGO_PASS", "")

_client = None
_collection = None


def get_workflow_log_collection():
    global _client, _collection
    if _collection is None:
        options: dict[str, Any] = {
            "host": MONGO_HOST,
            "port": MONGO_PORT,
            "serverSelectionTimeoutMS": 5000,
            "tz_aware": True,
        }
        if MONGO_USER:
            options.update(username=MONGO_USER, password=MONGO_PASS, authSource="admin")
        _client = MongoClient(**options)
        _collection = _client[MONGO_DATABASE][MONGO_WORKFLOW_LOG_COLLECTION]
        _collection.create_index(
            [("workflow_name", ASCENDING), ("_id", DESCENDING)],
            name="workflow_name_id",
        )
    return _collection


def record_workflow_run(run: dict[str, Any]):
    return get_workflow_log_collection().insert_one(run).inserted_id
