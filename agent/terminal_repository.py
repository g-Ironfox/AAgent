"""Persist explicit terminal output without publishing workflow events."""

import os
from datetime import datetime, timezone

from pymongo import MongoClient

_client = None
_collection = None


def get_terminal_collection():
    global _client, _collection
    if _collection is None:
        options = {
            "host": os.getenv("MONGO_HOST", "mongodb"),
            "port": int(os.getenv("MONGO_PORT", "27017")),
            "serverSelectionTimeoutMS": 5000,
            "tz_aware": True,
        }
        if os.getenv("MONGO_USER"):
            options.update(
                username=os.environ["MONGO_USER"],
                password=os.getenv("MONGO_PASS", ""),
                authSource="admin",
            )
        _client = MongoClient(**options)
        database = _client[os.getenv("MONGO_DATABASE", "agent")]
        _collection = database[os.getenv("MONGO_TERMINAL_COLLECTION", "terminal_messages")]
    return _collection


def append_terminal_output(content: str):
    if not isinstance(content, str) or not content.strip():
        raise ValueError("终端输出内容必须是非空字符串")
    document = {"role": "assistant", "content": content, "created_at": datetime.now(timezone.utc)}
    return get_terminal_collection().insert_one(document).inserted_id
