import os
from datetime import datetime, timezone

from bson import ObjectId
from bson.errors import InvalidId
from pymongo import ASCENDING, DESCENDING, MongoClient

MONGO_HOST = os.getenv("MONGO_HOST", "mongodb")
MONGO_PORT = int(os.getenv("MONGO_PORT", "27017"))
MONGO_USER = os.getenv("MONGO_USER")
MONGO_PASS = os.getenv("MONGO_PASS")
MONGO_DATABASE = os.getenv("MONGO_DATABASE", "agent")
MONGO_HISTORY_COLLECTION = os.getenv("QQ_AGENT_HISTORY_COLLECTION", "subagent_qq_history")
MONGO_DOCUMENT_COLLECTION = os.getenv("MONGO_DOCUMENT_COLLECTION", "documents")

_client = None
_collection = None


def get_history_collection():
    global _client, _collection
    if _collection is None:
        options = {"host": MONGO_HOST, "port": MONGO_PORT, "serverSelectionTimeoutMS": 5000, "tz_aware": True}
        if MONGO_USER:
            options.update(username=MONGO_USER, password=MONGO_PASS, authSource="admin")
        _client = MongoClient(**options)
        _collection = _client[MONGO_DATABASE][MONGO_HISTORY_COLLECTION]
        _collection.create_index([("created_at", DESCENDING)], name="created_at_desc")
        _collection.create_index([("event_type", ASCENDING), ("created_at", DESCENDING)], name="event_type_created_at")
    return _collection


def record_history(event: dict):
    document = {**event, "created_at": datetime.now(timezone.utc)}
    return get_history_collection().insert_one(document).inserted_id


def get_documents(document_ids: list[str]):
    object_ids = []
    for document_id in document_ids:
        try:
            object_ids.append(ObjectId(document_id))
        except (InvalidId, TypeError):
            continue
    if not object_ids:
        return []
    collection = get_history_collection().database[MONGO_DOCUMENT_COLLECTION]
    documents_by_id = {str(item["_id"]): item for item in collection.find({"_id": {"$in": object_ids}})}
    return [documents_by_id[document_id] for document_id in document_ids if document_id in documents_by_id]
