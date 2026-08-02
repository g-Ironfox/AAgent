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

def chat_with_deepseek():
    h=get_recent_history(limit=10)
    messages = [
        {"role": "system", "content": "你是一个办公助手"},
    ]

    for i in h[::-1]:
        payload=i.get('payload')
        if i['event_type']=='qq':
            if i['payload']["post_type"]=="message":
                if payload['group_id']:
                    messages.append({"role": "user", "content": f"<QQ event='msg' type='group' group_id={payload['group_id']} sender_id={payload['user_id']}>{payload['raw_message']}</QQ>"})
                else:
                    messages.append({"role": "user", "content": f"<QQ event='msg' type='private' sender_id={payload['user_id']}>{payload['raw_message']}</QQ>"})
        if i['event_type']=='tool_return':
            messages.append({"role":"user",'content':f"Tool {payload['tool']} args({json.dumps(payload['args'])}) result: {payload['result']}"})
        if i['event_type']=='webui':
            messages.append({"role":"system",'content':f"<Msg role='admin'>{payload['message']}</Msg>"})

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
        return "[-]余额不足","",[]
    
    tool_calls=message.get('tool_calls') if message.get('tool_calls') else []
    reasoning=message.get('reasoning_content') if message.get('reasoning_content') else ""
    return message['content'],reasoning,tool_calls