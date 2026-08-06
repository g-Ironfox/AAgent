# agent/task_worker.py
import os
import time
import traceback
from datetime import datetime, timezone
import json
from pathlib import Path
import tools.qq

from history_repository import record_history,get_recent_history
from queue_client import (
    AGENT_QUEUE_NAME,
    clear_legacy_system_prompt,
    get_legacy_system_prompt,
    get_system_prompt,
    pop_from_queue,
    insert_to_queue,
    publish_to_queue,
    set_system_prompt,
    set_worker_status,
)
from llm import chat_with_deepseek,chat_with_llama_cpp
from tools.tool import execute_tool
from tools.documents import system_documents_prompt


TARGET_USER_ID = os.environ["QQ_TARGET_USER_ID"]
BOT_ID = os.environ["QQ_BOT_ID"]
SETTINGS_PATH = Path(__file__).parent / "settings.json"

def default_system_prompt() -> str:
    """settings.json 仅作为首次启动/无缓存时的默认种子,运行时真源在 Redis"""
    settings = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    system_prompt = settings.get("system_prompt")
    if not isinstance(system_prompt, str) or not system_prompt:
        raise ValueError("settings.json system_prompt must be a non-empty string")
    return system_prompt

def read_system_prompt() -> str:
    system_prompt = get_system_prompt()
    if system_prompt is None:
        return default_system_prompt()
    return system_prompt

def apply_system_prompt(system_prompt: str):
    set_system_prompt(system_prompt)

def initialize_system_prompt():
    if get_system_prompt() is not None:
        return
    legacy = get_legacy_system_prompt()
    if legacy:
        set_system_prompt(legacy)
        clear_legacy_system_prompt()
        return
    set_system_prompt(default_system_prompt())

def handle_task(e: dict):
    def qq(e):
        print(f"QQ事件:{e['payload']}")
        if e['payload']['post_type']=="message":
            raw_message = e['payload'].get("raw_message", "")
            group_id = e['payload'].get("group_id")
            user_id = e['payload'].get("user_id")
            if not isinstance(raw_message, str):
                raw_message = ""
        
            if str(user_id) == TARGET_USER_ID and (not group_id or f'[CQ:at,qq={BOT_ID}]' in raw_message):
                
                if not raw_message:
                    print("空消息，跳过:", e['payload'])
                    return
        
                print("收到任务:", e['payload'])
        
                e={
                    "event_type":"active",
                    "payload":{
                        "user_id":user_id,
                        "group_id":group_id,
                    }
                }
                publish_to_queue(AGENT_QUEUE_NAME,e)
    def terminal(e):
        e={
            "event_type":"active",
            "payload":{
            }
        }
        publish_to_queue(AGENT_QUEUE_NAME,e)
    def tool(e):
        print(f"工具事件:{e['payload']}")
        tool_id = e['payload']['id']
        tool_name = e['payload']['tool']
        tool_args = e['payload']['args']
        try:
            result = execute_tool(tool_id, tool_name,tool_args )
            r_e={
                "event_type":"tool_return",
                "payload":
                {
                    "id": tool_id,
                    "tool": tool_name,
                    "args":tool_args,
                    "result": result,
                    "success": True,
                }
            }
        except Exception as error:
            r_e={
                "event_type":"tool_return",
                "payload":
                {
                    "id": tool_id,
                    "tool": tool_name,
                    "args":tool_args,
                    "result": f"Error:{str(error)}",
                    "success": False,
                }
            }
        insert_to_queue(AGENT_QUEUE_NAME,r_e)
    def setting(e):
        system_prompt = e['payload'].get('system_prompt')
        if isinstance(system_prompt, str) and system_prompt:
            apply_system_prompt(system_prompt)
    def active(e):
        system_prompt = read_system_prompt().replace("{{TARGET_USER_ID}}", TARGET_USER_ID).replace("{{BOT_ID}}", BOT_ID)
        system_prompt = system_prompt.replace("{{SYSTEM_DOCUMENTS_PROMPT}}",system_documents_prompt())
        skills=[]

        h=get_recent_history(limit=16)
        messages = [
            {"role": "system", "content": system_prompt},
            {"role":"user","content":"\n".join(skills)}
        ]

        context=[]


        for i in h[::-1]:
            payload=i.get('payload')
            if i['event_type']=='qq':
                if i['payload']["post_type"]=="message":
                    if payload['group_id']:
                        context.append(f"<QQ event='msg' type='group' group_id={payload['group_id']} sender_id={payload['user_id']}>{payload['raw_message']}</QQ>")
                    else:
                        context.append(f"<QQ event='msg' type='private' sender_id={payload['user_id']}>{payload['raw_message']}</QQ>")
            if i['event_type']=='tool_return':
                context.append(f"<tool name={payload['tool']} args={json.dumps(payload['args'],ensure_ascii=False)}> result: {payload['result']}</tool>")
            if i['event_type']=='terminal':
                context.append(f"<Command>{payload['message']}</Command>")

            if i['event_type']=='response':
                if context:
                    messages.append({"role":"user","content":"\n".join(context)})
                    context=[]
                messages.append({"role":"assistant","content":payload["content"] or ""})
        if context:
            messages.append({"role":"user","content":"\n".join(context)})
        content,reasoning,tool_calls=chat_with_deepseek(messages)
        e={'event_type':"response",
        "payload":{
                "content":content,
                "reasoning":reasoning,
                "tool_calls":tool_calls,
                "context":messages
            }
        }
        if tool_calls:
            e2={
                    "event_type":"active",
                    "payload":{
                    }
                }
            insert_to_queue(AGENT_QUEUE_NAME,e2,e)
        else:
            insert_to_queue(AGENT_QUEUE_NAME,e)
    def tool_return(e):
        pass
    def response(e):
        tool_calls=e["payload"].get("tool_calls")
        
        if tool_calls:
            events=[]
            for i in tool_calls:
                try:
                    args=json.loads(i["function"]["arguments"])
                except (json.JSONDecodeError, TypeError):
                    events.append({
                        "event_type":"tool_return",
                        "payload":{
                            "id":i['id'],
                            "tool":i['function']['name'],
                            "args":i["function"]["arguments"],
                            "result":"Error: 工具参数 JSON 解析失败",
                            "success": False,
                        }
                    })
                    continue
                e={
                    "event_type":"tool",
                    "payload":{'id':i['id'],
                        'tool':i['function']['name'],
                        "args":args
                    }
                }
                events.append(e)
            insert_to_queue(AGENT_QUEUE_NAME,*events[::-1])
    handle_map = {
        "qq": qq,
        "terminal": terminal,
        "tool": tool,
        "tool_return": tool_return,
        "setting": setting,
        "active": active,
        "response": response,
    }

    record_history(e)
    handler = handle_map.get(e['event_type'])
    handler(e)
    

def main():
    print("Agent worker started...")
    initialize_system_prompt()
    while True:
        try:
            set_worker_status({
                "state": "idle",
                "updated_at": datetime.now(timezone.utc).isoformat(),
            })
            task = pop_from_queue(AGENT_QUEUE_NAME, timeout=5)
            if task is None:
                continue
            set_worker_status({
                "state": "processing",
                "event": task,
                "started_at": datetime.now(timezone.utc).isoformat(),
            })
            try:
                handle_task(task)
            finally:
                set_worker_status({
                    "state": "idle",
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                })
        except Exception as e:
            print("agent处理失败:", e)
            traceback.print_exc()
            time.sleep(2)


if __name__ == "__main__":
    main()