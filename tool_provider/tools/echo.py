from typing import Any

from tool import Tool, ToolContext


class EchoTool(Tool):
    name = "system.echo"
    description = "返回收到的文本，用于验证 Tool Provider 调用链路。"
    input_schema = {
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
        "additionalProperties": False,
    }
    output_schema = {
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
        "additionalProperties": False,
    }
    annotations = {"readOnlyHint": True}

    def execute(self, arguments: dict[str, Any], context: ToolContext) -> Any:
        return {"text": arguments["text"]}