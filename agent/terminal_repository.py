"""Persist explicit terminal output without publishing workflow events."""

import os
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone

from pymongo import MongoClient

current_terminal_process_id = ContextVar("terminal_process_id", default=None)


@contextmanager
def terminal_process_context(terminal_process_id):
    token = current_terminal_process_id.set(terminal_process_id)
    try:
        yield
    finally:
        current_terminal_process_id.reset(token)


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


def append_terminal_output(content: str, terminal_process_id: str):
    if not isinstance(content, str) or not content.strip():
        raise ValueError("终端输出内容必须是非空字符串")
    document = {"role": "assistant", "content": content, "created_at": datetime.now(timezone.utc)}
    if not isinstance(terminal_process_id, str) or not terminal_process_id.strip():
        raise ValueError("terminal_process_id must be a non-empty string")
    document["terminal_process_id"] = terminal_process_id
    return get_terminal_collection().insert_one(document).inserted_id
