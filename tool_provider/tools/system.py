from typing import Any

from tool import Tool, ToolContext


class EchoTool(Tool):
    name = "system.echo"
    description = "原样返回输入值，用于调试 Tool 调用链路。"
    input_schema = {
        "type": "object",
        "properties": {"value": {"description": "要原样返回的任意 JSON 值"}},
        "required": ["value"],
        "additionalProperties": False,
    }
    output_schema = {
        "type": "object",
        "properties": {"value": {"description": "原样返回的输入值"}},
        "required": ["value"],
        "additionalProperties": False,
    }

    def execute(self, arguments: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        return {"value": arguments["value"]}