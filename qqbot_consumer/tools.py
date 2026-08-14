import json
import os
from itertools import cycle
from queue_client import MAIN_AGENT_QUEUE_NAME,publish_to_queue

import requests

tools = []
tool_handlers = {}


def tool(description, parameters=None, name=None):
    def register(function):
        tool_name = name or function.__name__
        if tool_name in tool_handlers:
            raise ValueError(f"工具已注册: {tool_name}")

        tools.append({
            "type": "function",
            "function": {
                "name": tool_name,
                "description": description,
                "parameters": parameters or {"type": "object", "properties": {}}
            }
        })
        tool_handlers[tool_name] = function
        return function

    return register

"""
@tool(
    "发送群消息",
    {
        "type": "object",
        "properties": {
            "group_id": {"type": "string", "description": "群id"},
            "message": {"type": "string", "description": "消息内容"}
        },
        "required": ["group_id","message"]
    }
)
def send_group_message(group_id,message):
    e = {
        "event_type":"application",
        "payload":{
            "tool_name":"send_group_message",
            "arguments":json.dumps({"group_id":group_id,"messgae":message},ensure_ascii=False)
        }
    }
    publish_to_queue(MAIN_AGENT_QUEUE_NAME,e)
    return "请求中"
"""

def execute_tool(id,tool,args):
    handler = tool_handlers.get(tool)
    if handler is None:
        return f"未知工具: {tool}"

    result = handler(**args)

    # 将结果转为字符串（如果是列表等复杂类型，可做适当格式化）
    if isinstance(result, (list, dict)):
        result = json.dumps(result, ensure_ascii=False)
    elif result is None:
        result = "执行失败，未获取到数据"
    return str(result)