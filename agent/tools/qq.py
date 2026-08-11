from tools.tool import tool
from tools.qqapi import send_group_msg,send_private_msg,get_group_member_info,get_group_list,get_group_msg_history

from queue_client import publish_to_queue,AGENT_QUEUE_NAME

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
def qq_send_group_msg(group_id, message):
    e={
        "event_type":"qq",
        "payload":{
            "post_type":"send",
            "group_id": group_id,
            "raw_message": message,
            "message": {
                "type": "text",
                "data": {
                "text": message
                }
            }
        }
    }
    publish_to_queue(AGENT_QUEUE_NAME,e)
    return send_group_msg(group_id, message)


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
def qq_send_private_msg(user_id, message):
    e={
        "event_type":"qq",
        "payload":{
            "post_type":"send",
            "target_id": user_id,
            "raw_message": message,
            "message": {
                "type": "text",
                "data": {
                "text": message
                }
            }
        }
    }
    publish_to_queue(AGENT_QUEUE_NAME,e)
    return send_private_msg(user_id, message)
