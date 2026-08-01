# agent/llm.py
import os

import requests
from tool import *
from queue_client import insert_to_queue,AGENT_QUEUE_NAME
from history_repository import get_recent_history

DEEPSEEK_BASE_URL = os.environ["DEEPSEEK_BASE_URL"].rstrip("/")
DEEPSEEK_API_KEY = os.environ["DEEPSEEK_API_KEY"]
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-pro")

def send_messages(messages,url,key,model):
    """发送请求到 DeepSeek 并返回 message 对象"""
    payload = {
        "model": model,
        "messages": messages,
        "tools": tools
    }
    resp = requests.post(
        f"{url.rstrip('/')}/chat/completions",
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json"
        },
        json=payload,
        timeout=(5, 60)
    )
    if resp.status_code == 402:
        return 402
    resp.raise_for_status()
    print(resp.json())
    return resp.json()["choices"][0]["message"]

def chat_with_deepseek(user_id,group_id):
    h=get_recent_history(limit=10)
    messages = [
        {"role": "system", "content": "你是一个办公助手"},
    ]

    for i in h[::-1]:
        payload=i.get('payload')
        if i['event_type']=='qq':
            if payload['group_id']:
                messages.append({"role": "user", "content": f"<groupmsg group={payload['group_id']} sender={payload['user_id']}>{payload['raw_message']}</groupmsg>"})
            else:
                messages.append({"role": "user", "content": f"<privatemsg sender={payload['user_id']}>{payload['raw_message']}</privatemsg>"})
        if i['event_type']=='tool_return':
            messages.append({"role":"user",'content':f"Tool {payload['tool']} args({json.dumps(payload['args'])}) result: {payload['result']}"})
        if i['event_type']=='response':
            messages.append({"role":"assistant","content":payload["content"]})
    print(messages)
    message = send_messages(
        messages,
        DEEPSEEK_BASE_URL,
        DEEPSEEK_API_KEY,
        DEEPSEEK_MODEL
    )

    if message ==402:
        return "[-]余额不足"
    
    tool_calls=message.get('tool_calls') if message.get('tool_calls') else []

    e={'event_type':"response",
       "payload":{
           "content":message['content'],
            "reasoning_content":message.get('reasoning_content'),
            "tool_calls":tool_calls
        }
    }
    if tool_calls:
        e2={
                "event_type":"active",
                "payload":{
                    "user_id":user_id,
                    "group_id":group_id
                }
            }
        insert_to_queue(AGENT_QUEUE_NAME,e2,e)
    else:
        insert_to_queue(AGENT_QUEUE_NAME,e)

    print(message['content'],message.get('reasoning_content'),tool_calls)
    return message['content']