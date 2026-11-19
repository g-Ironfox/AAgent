"""Persist explicit terminal output without publishing workflow events."""

import os
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone

from pymongo import ASCENDING, MongoClient

current_terminal_process_id = ContextVar("terminal_process_id", default=None)
current_terminal_id = ContextVar("terminal_id", default=None)


@contextmanager
def terminal_process_context(terminal_process_id, terminal_id):
    process_token = current_terminal_process_id.set(terminal_process_id)
    terminal_token = current_terminal_id.set(terminal_id)
    try:
        yield
    finally:
        current_terminal_id.reset(terminal_token)
        current_terminal_process_id.reset(process_token)


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


def append_terminal_output(
    content: str,
    terminal_id: str,
    terminal_process_id: str | None = None,
):
    if not isinstance(content, str) or not content.strip():
        raise ValueError("终端输出内容必须是非空字符串")
    document = {"role": "assistant", "content": content, "created_at": datetime.now(timezone.utc)}
    if not isinstance(terminal_id, str) or not terminal_id.strip():
        raise ValueError("terminal_id must be a non-empty string")
    document["terminal_id"] = terminal_id
    if terminal_process_id is not None:
        if not isinstance(terminal_process_id, str) or not terminal_process_id.strip():
            raise ValueError("terminal_process_id must be a non-empty string")
        document["terminal_process_id"] = terminal_process_id
    return get_terminal_collection().insert_one(document).inserted_id


def read_terminal_input(terminal_id: str) -> list[str]:
    """Read all user input for one terminal, oldest first, without consuming it."""
    if not isinstance(terminal_id, str) or not terminal_id.strip():
        raise ValueError("terminal_id must be a non-empty string")
    documents = get_terminal_collection().find(
        {"terminal_id": terminal_id, "role": "user"},
        {"content": 1},
    ).sort([("created_at", ASCENDING), ("_id", ASCENDING)])
    contents = []
    for document in documents:
        content = document.get("content")
        if not isinstance(content, str):
            raise ValueError("terminal user input content must be text")
        contents.append(content)
    return contents
