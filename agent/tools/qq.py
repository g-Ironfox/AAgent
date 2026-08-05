from tools.tool import tool
from tools.qqapi import send_group_msg as qq_send_group_msg
from tools.qqapi import send_private_msg as qq_send_private_msg

@tool(
    "发送群消息",
    {
        "type": "object",
        "properties": {
            "group_id": {"type": "string", "description": "群号"},
            "message": {"type": "string", "description": "消息内容 `[CQ:at,qq=QQ号]`可用于艾特用户"}
        },
        "required": ["group_id", "message"]
    }
)
def send_group_msg(group_id, message):
    return qq_send_group_msg(group_id, message)


@tool(
    "发送私聊消息",
    {
        "type": "object",
        "properties": {
            "user_id": {"type": "string", "description": "QQ号"},
            "message": {"type": "string", "description": "消息内容 `[CQ:at,qq=QQ号]`可用于艾特用户"}
        },
        "required": ["user_id", "message"]
    }
)
def send_private_msg(user_id, message):
    return qq_send_private_msg(user_id, message)
