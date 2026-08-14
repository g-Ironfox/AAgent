import json
import os
from itertools import cycle


import requests

DEEPSEEK_BASE_URL = os.environ["DEEPSEEK_BASE_URL"].rstrip("/")
DEEPSEEK_API_KEY = os.environ["DEEPSEEK_API_KEY"]

KIMI_BASE_URL = os.environ["KIMI_BASE_URL"].rstrip("/")
KIMI_API_KEY = os.environ["KIMI_API_KEY"]

ZAI_API_KEY = os.environ["ZAI_API_KEY"]
TAVILY_API_KEYS = [
    key.strip()
    for key in os.environ["TAVILY_API_KEYS"].split(",")
    if key.strip()
]

BOCHA_BASE_URL = os.environ["BOCHA_BASE_URL"].rstrip("/")
BOCHA_API_KEY = os.environ["BOCHA_API_KEY"]

if not TAVILY_API_KEYS:
    raise RuntimeError("TAVILY_API_KEYS must contain at least one API key")

TAVILY_API_KEY_CYCLE = cycle(TAVILY_API_KEYS)

registered_tools = []
tool_handlers = {}


def tool(description, parameters=None, name=None):
    def register(function):
        tool_name = name or function.__name__
        if tool_name in tool_handlers:
            raise ValueError(f"工具已注册: {tool_name}")

        registered_tools.append({
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


@tool("查询 DeepSeek API 账户余额", name="get_deepseek_balance")
def deepseekBalance():
    url = f"{DEEPSEEK_BASE_URL}/v1/user/balance"
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json"
    }

    response = requests.get(url, headers=headers, timeout=(5, 30))
    if  response.status_code == 200:
        return response.json()['balance_infos'][0]['total_balance']
    return None

@tool("查询 Kimi API 账户余额", name="get_kimi_balance")
def kimiBalance():
    url = f"{KIMI_BASE_URL}/v1/users/me/balance"
    headers = {
        "Authorization": f"Bearer {KIMI_API_KEY}",
        "Content-Type": "application/json"
    }

    response = requests.get(url, headers=headers, timeout=(5, 30))
    if  response.status_code == 200:
        return str(response.json()['data']['available_balance']) #kimi api返回的是int
    return None


@tool(
    "使用 Tavily 搜索引擎进行网络搜索，适合获取实时或最新信息",
    {
        "type": "object",
        "properties": {
            "keyword": {"type": "string", "description": "搜索关键词"}
        },
        "required": ["keyword"]
    }
)
def tavily_search(keyword):
    url = "https://api.tavily.com/search"
    payload = {
        "query": keyword,
        "search_depth": "advanced",
        "max_results": 10
    }

    for _ in TAVILY_API_KEYS:
        api_key = next(TAVILY_API_KEY_CYCLE)
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            response.raise_for_status()
            return response.json().get("results", [])
        except requests.exceptions.RequestException as e:
            print(f"Tavily 请求失败，切换下一个 Key: {e}")

    return []

def bocha_search(keyword):
    url = f"{BOCHA_BASE_URL.rstrip('/')}/v1/web-search"

    payload = json.dumps({
        "query": keyword,
        "summary": True,
        "count": 10
    })

    headers = {
    'Authorization': f'Bearer {BOCHA_API_KEY}',
    'Content-Type': 'application/json'
    }

    response = requests.request("POST", url, headers=headers, data=payload)

    print(response.json())

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