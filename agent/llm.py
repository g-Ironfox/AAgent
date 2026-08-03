# agent/llm.py
import os

import requests
from tool import tools

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

def chat_with_deepseek(messages):
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

def chat_with_llama_cpp(messages):
    message = send_messages(
        messages,
        "http://127.0.0.1:8080",
        "",
        ""
    )
    
    tool_calls=message.get('tool_calls') if message.get('tool_calls') else []
    reasoning=message.get('reasoning_content') if message.get('reasoning_content') else ""
    return message['content'],reasoning,tool_calls
