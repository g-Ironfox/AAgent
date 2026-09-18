from typing import Any

from tool import Tool, ToolContext
from tools.qqapi import send_group_msg, send_private_msg


class QQSendGroupMessageTool(Tool):
    name = "qq.send_group_msg"
    description = "发送 QQ 群消息。"
    input_schema = {
        "type": "object",
        "properties": {
            "group_id": {"type": "string", "description": "群号"},
            "message": {"type": "string", "description": "消息内容"},
        },
        "required": ["group_id", "message"],
        "additionalProperties": False,
    }
    output_schema = {
        "type": "object",
        "properties": {
            "message_id": {
                "type": "integer",
                "description": "已发送消息的 ID",
                "x-workflow-port-type": "content",
            }
        },
        "required": ["message_id"],
        "additionalProperties": False,
    }

    def execute(self, arguments: dict[str, Any], context: ToolContext) -> dict[str, int]:
        result = send_group_msg(arguments["group_id"], arguments["message"])
        return {"message_id": result["message_id"]}


class QQSendPrivateMessageTool(Tool):
    name = "qq.send_private_msg"
    description = "发送 QQ 私聊消息。"
    input_schema = {
        "type": "object",
        "properties": {
            "user_id": {"type": "string", "description": "QQ 号"},
            "message": {"type": "string", "description": "消息内容"},
        },
        "required": ["user_id", "message"],
        "additionalProperties": False,
    }
    output_schema = {
        "type": "object",
        "properties": {
            "message_id": {
                "type": "integer",
                "description": "已发送消息的 ID",
                "x-workflow-port-type": "content",
            }
        },
        "required": ["message_id"],
        "additionalProperties": False,
    }

    def execute(self, arguments: dict[str, Any], context: ToolContext) -> dict[str, int]:
        result = send_private_msg(arguments["user_id"], arguments["message"])
        return {"message_id": result["message_id"]}