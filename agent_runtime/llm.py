# agent_runtime/llm.py
import copy
import hashlib
import os
import re

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

def _prepare_tool_names(payload: dict) -> tuple[dict, dict[str, str]]:
    """Translate internal tool names at the API boundary, including history."""
    payload = copy.deepcopy(payload)
    functions = [
        tool["function"] for tool in payload.get("tools") or []
        if tool.get("type") == "function"
    ]
    for message in payload.get("messages", []):
        functions.extend(call["function"] for call in message.get("tool_calls") or [])
        if message.get("role") == "tool" and "name" in message:
            functions.append(message)
    choice = payload.get("tool_choice")
    if isinstance(choice, dict) and choice.get("type") == "function":
        functions.append(choice["function"])

    names = {function["name"] for function in functions}
    aliases = {}
    reserved = set(names)
    for name in sorted(names):
        # Use the conservative OpenAI-compatible limit across providers.
        if re.fullmatch(r"[A-Za-z0-9_-]{1,64}", name):
            continue
        stem = re.sub(r"[^A-Za-z0-9_-]", "_", name)[:51] or "tool"
        attempt = 0
        while True:
            identity = name if attempt == 0 else f"{name}:{attempt}"
            digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:12]
            alias = f"{stem}_{digest}"
            if alias not in reserved:
                break
            attempt += 1
        aliases[name] = alias
        reserved.add(alias)
    for function in functions:
        function["name"] = aliases.get(function["name"], function["name"])
    return payload, {alias: name for name, alias in aliases.items()}


def openai_llm_api(messages,model,url,key,tools=registered_tools,extra={}):
    """发送 OpenAI-compatible chat completion 请求并返回 message 对象"""
    payload = {
        "model": model,
        "messages": messages,
        "tools": tools,
        **extra
    }
    payload, original_names = _prepare_tool_names(payload)
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
    try:
        resp.raise_for_status()
    except requests.HTTPError as error:
        try:
            body = resp.json()
        except ValueError:
            detail = resp.text
        else:
            detail = str(body.get("error", body) if isinstance(body, dict) else body)
        if key:
            detail = detail.replace(key, "[REDACTED]")
        raise requests.HTTPError(
            f"{error}; provider error: {detail[:2000]}",
            request=error.request, response=resp,
        ) from error
    res=resp.json()["choices"][0]["message"]
    tool_calls=copy.deepcopy(res.get('tool_calls') or [])
    for call in tool_calls:
        # Some compatible providers include the stream assembly index even in
        # completed messages. It is not part of a persisted tool-call message.
        call.pop("index", None)
        function = call["function"]
        function["name"] = original_names.get(function["name"], function["name"])
    reasoning=res.get('reasoning_content') if res.get('reasoning_content') else ""

    return res['content'],reasoning,tool_calls

def _thinking_options(config: dict, think: bool) -> dict:
    if think:
        return {}

    provider = " ".join(
        str(config.get(key, "")) for key in ("provider", "model", "base_url")
    ).lower()
    if "deepseek" in provider:
        return {"thinking": {"type": "disabled"}}
    if "qwen" in provider or "dashscope" in provider:
        return {"enable_thinking": False}
    return {"reasoning_effort": "none"}


def chat_with_model(messages, model_id, tools=registered_tools, think=True):
    config = _model_config(model_id)
    content,reasoning,tool_calls = openai_llm_api(
        messages,
        config["model"],
        config["base_url"],
        config.get("api_key", ""),
        tools,
        extra=_thinking_options(config, think),
    )

    if content==402:
        return "[-]余额不足","",[]
    
    if not think:
        reasoning = ""

    return content,reasoning,tool_calls
