import os
from typing import Any

from bson import ObjectId
from bson.errors import InvalidId
from pymongo import MongoClient, ReturnDocument

from tool import Tool, ToolContext


MAX_DOCUMENT_TITLE_CHARS = 200
MAX_DOCUMENT_CONTENT_CHARS = 1_000_000

mongo_kwargs: dict[str, Any] = {
    "host": os.getenv("MONGO_HOST", "mongodb"),
    "port": int(os.getenv("MONGO_PORT", "27017")),
    "serverSelectionTimeoutMS": 5000,
    "tz_aware": True,
}
if os.getenv("MONGO_USER"):
    mongo_kwargs.update(
        username=os.environ["MONGO_USER"],
        password=os.getenv("MONGO_PASS", ""),
        authSource="admin",
    )

mongo_client = MongoClient(**mongo_kwargs)
documents = mongo_client[
    os.getenv("MONGO_DATABASE", "agent")
][os.getenv("MONGO_DOCUMENT_COLLECTION", "documents")]


def _object_id(doc_id: str) -> ObjectId:
    try:
        return ObjectId(doc_id)
    except InvalidId as error:
        raise ValueError(f"无效的文档 ID: {doc_id}") from error


def _find_document(doc_id: str) -> dict[str, Any]:
    document = documents.find_one({"_id": _object_id(doc_id)})
    if document is None:
        raise ValueError(f"文档不存在: {doc_id}")
    return document


def _serialize(document: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(document["_id"]),
        "title": document.get("title", ""),
        "content": document.get("content", ""),
        "pinned": bool(document.get("pinned", False)),
        "created_at": document.get("created_at").isoformat() if document.get("created_at") else None,
        "updated_at": document.get("updated_at").isoformat() if document.get("updated_at") else None,
    }


DOCUMENT_SCHEMA = {
    "type": "object",
    "properties": {
        "id": {"type": "string"},
        "title": {"type": "string"},
        "content": {"type": "string", "x-workflow-port-type": "content"},
        "pinned": {"type": "boolean"},
        "created_at": {"type": ["string", "null"]},
        "updated_at": {"type": ["string", "null"]},
    },
    "required": ["id", "title", "content", "pinned", "created_at", "updated_at"],
    "additionalProperties": False,
}


class DocumentQueryByNameTool(Tool):
    name = "documents.query_by_name"
    description = "通过标题查询文档，返回所有同名文档。"
    input_schema = {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "文档标题",
                "minLength": 1,
                "maxLength": MAX_DOCUMENT_TITLE_CHARS,
            }
        },
        "required": ["title"],
        "additionalProperties": False,
    }
    output_schema = {
        "type": "object",
        "properties": {"documents": {"type": "array", "items": DOCUMENT_SCHEMA}},
        "required": ["documents"],
        "additionalProperties": False,
    }

    def execute(self, arguments: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        matches = documents.find({"title": arguments["title"]})
        return {"documents": [_serialize(document) for document in matches]}


class DocumentQueryByIdTool(Tool):
    name = "documents.query_by_id"
    description = "通过文档 ID 查询文档。"
    input_schema = {
        "type": "object",
        "properties": {"doc_id": {"type": "string", "description": "文档 ID"}},
        "required": ["doc_id"],
        "additionalProperties": False,
    }
    output_schema = DOCUMENT_SCHEMA

    def execute(self, arguments: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        return _serialize(_find_document(arguments["doc_id"]))


class DocumentCreateTool(Tool):
    name = "documents.create"
    description = "新建文档。"
    input_schema = {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "文档标题",
                "default": "未命名文档",
                "minLength": 1,
                "maxLength": MAX_DOCUMENT_TITLE_CHARS,
            },
            "content": {
                "type": "string",
                "description": "文档内容",
                "default": "",
                "maxLength": MAX_DOCUMENT_CONTENT_CHARS,
            },
        },
        "additionalProperties": False,
    }
    output_schema = DOCUMENT_SCHEMA

    def execute(self, arguments: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        document = {
            "title": arguments.get("title", "未命名文档"),
            "content": arguments.get("content", ""),
            "pinned": False,
            "created_at": now,
            "updated_at": now,
        }
        document["_id"] = documents.insert_one(document).inserted_id
        return _serialize(document)


class DocumentAppendTool(Tool):
    name = "documents.append"
    description = "在文档末尾追加内容。"
    input_schema = {
        "type": "object",
        "properties": {
            "doc_id": {"type": "string", "description": "文档 ID"},
            "append_content": {"type": "string", "description": "追加内容"},
        },
        "required": ["doc_id", "append_content"],
        "additionalProperties": False,
    }
    output_schema = DOCUMENT_SCHEMA

    def execute(self, arguments: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        from datetime import datetime, timezone

        current = _find_document(arguments["doc_id"])
        content = current.get("content", "") + arguments["append_content"]
        if len(content) > MAX_DOCUMENT_CONTENT_CHARS:
            raise ValueError(f"文档内容过长，最大允许 {MAX_DOCUMENT_CONTENT_CHARS} 字符")
        updated = documents.find_one_and_update(
            {"_id": current["_id"]},
            {"$set": {"content": content, "updated_at": datetime.now(timezone.utc)}},
            return_document=ReturnDocument.AFTER,
        )
        return _serialize(updated)


class DocumentRewriteTool(Tool):
    name = "documents.rewrite"
    description = "重写文档内容。"
    input_schema = {
        "type": "object",
        "properties": {
            "doc_id": {"type": "string", "description": "文档 ID"},
            "content": {
                "type": "string",
                "description": "新文档内容",
                "maxLength": MAX_DOCUMENT_CONTENT_CHARS,
            },
        },
        "required": ["doc_id", "content"],
        "additionalProperties": False,
    }
    output_schema = DOCUMENT_SCHEMA

    def execute(self, arguments: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        from datetime import datetime, timezone

        current = _find_document(arguments["doc_id"])
        updated = documents.find_one_and_update(
            {"_id": current["_id"]},
            {"$set": {"content": arguments["content"], "updated_at": datetime.now(timezone.utc)}},
            return_document=ReturnDocument.AFTER,
        )
        return _serialize(updated)


class DocumentRenameTool(Tool):
    name = "documents.rename"
    description = "重命名文档。"
    input_schema = {
        "type": "object",
        "properties": {
            "doc_id": {"type": "string", "description": "文档 ID"},
            "title": {
                "type": "string",
                "description": "新文档标题",
                "minLength": 1,
                "maxLength": MAX_DOCUMENT_TITLE_CHARS,
            },
        },
        "required": ["doc_id", "title"],
        "additionalProperties": False,
    }
    output_schema = DOCUMENT_SCHEMA

    def execute(self, arguments: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        from datetime import datetime, timezone

        current = _find_document(arguments["doc_id"])
        updated = documents.find_one_and_update(
            {"_id": current["_id"]},
            {"$set": {"title": arguments["title"], "updated_at": datetime.now(timezone.utc)}},
            return_document=ReturnDocument.AFTER,
        )
        return _serialize(updated)


class DocumentPinTool(Tool):
    name = "documents.pin"
    description = "设置文档的钉住状态。"
    input_schema = {
        "type": "object",
        "properties": {
            "doc_id": {"type": "string", "description": "文档 ID"},
            "pinned": {"type": "boolean", "description": "是否钉住"},
        },
        "required": ["doc_id", "pinned"],
        "additionalProperties": False,
    }
    output_schema = DOCUMENT_SCHEMA

    def execute(self, arguments: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        current = _find_document(arguments["doc_id"])
        updated = documents.find_one_and_update(
            {"_id": current["_id"]},
            {"$set": {"pinned": arguments["pinned"]}},
            return_document=ReturnDocument.AFTER,
        )
        return _serialize(updated)