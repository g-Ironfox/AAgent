# agent/llm.py
import os

import requests
from tools.tool import registered_tools

DEEPSEEK_BASE_URL = os.environ["DEEPSEEK_BASE_URL"].rstrip("/")
DEEPSEEK_API_KEY = os.environ["DEEPSEEK_API_KEY"]
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-pro")

def openai_llm_api(messages,model,url,key,tools=registered_tools,extra={}):
    """发送请求到 DeepSeek 并返回 message 对象"""
    payload = {
        "model": model,
        "messages": messages,
        "tools": tools,
        **extra
    }
    resp = requests.post(
        f"{url.rstrip('/')}/chat/completions",
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json"
        },
        json=payload,
        timeout=(5, 90)
    )
    if resp.status_code == 402:
        return 402,None,None
    resp.raise_for_status()
    print(resp.json())
    res=resp.json()["choices"][0]["message"]
    tool_calls=res.get('tool_calls') if res.get('tool_calls') else []
    reasoning=res.get('reasoning_content') if res.get('reasoning_content') else ""

    return res['content'],reasoning,tool_calls

def chat_with_deepseek(messages,tools=registered_tools):
    content,reasoning,tool_calls = openai_llm_api(
        messages,
        DEEPSEEK_MODEL,
        DEEPSEEK_BASE_URL,
        DEEPSEEK_API_KEY,
        tools,
    )

    if content==402:
        return "[-]余额不足","",[]
    
    return content,reasoning,tool_calls