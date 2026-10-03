# agent/llm.py
import os

import requests
from bson import ObjectId
from bson.errors import InvalidId
from pymongo import MongoClient
from tools.tool import registered_tools


def _model_config(model_id: str) -> dict:
    try:
        if not isinstance(model_id, str) or not model_id:
            raise InvalidId(model_id)
        object_id = ObjectId(model_id)
    except (InvalidId, TypeError) as error:
        raise ValueError(f"llm model id is invalid: {model_id}") from error

    mongo_kwargs = {
        "host": os.getenv("MONGO_HOST", "mongodb"),
        "port": int(os.getenv("MONGO_PORT", "27017")),
        "serverSelectionTimeoutMS": 5000,
    }
    if os.getenv("MONGO_USER"):
        mongo_kwargs.update(
            username=os.environ["MONGO_USER"],
            password=os.getenv("MONGO_PASS", ""),
            authSource="admin",
        )
    with MongoClient(**mongo_kwargs) as client:
        config = client[os.getenv("MONGO_DATABASE", "agent")][
            os.getenv("MONGO_MODEL_COLLECTION", "models")
        ].find_one({"_id": object_id, "enabled": True}, {"_id": 0})
    if config is None:
        raise ValueError(f"llm model is not found or disabled: {model_id}")
    return config

def openai_llm_api(messages,model,url,key,tools=registered_tools,extra={}):
    """发送 OpenAI-compatible chat completion 请求并返回 message 对象"""
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

def chat_with_model(messages, model_id, tools=registered_tools):
    config = _model_config(model_id)
    content,reasoning,tool_calls = openai_llm_api(
        messages,
        config["model"],
        config["base_url"],
        config.get("api_key", ""),
        tools,
    )

    if content==402:
        return "[-]余额不足","",[]
    
    return content,reasoning,tool_calls