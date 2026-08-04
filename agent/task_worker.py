# agent/task_worker.py
import os
import time
import traceback
from datetime import datetime, timezone
import json
from pathlib import Path

from history_repository import record_history,get_recent_history
from queue_client import (
    AGENT_QUEUE_NAME,
    get_system_prompt,
    pop_from_queue,
    insert_to_queue,
    publish_to_queue,
    set_system_prompt,
    set_worker_status,
)
from llm import chat_with_deepseek,chat_with_llama_cpp
from qqapi import send_group_msg, send_private_msg
from tool import execute_tool, deepseekBalance, kimiBalance, tavily_search

TARGET_USER_ID = os.environ["QQ_TARGET_USER_ID"]
BOT_ID = os.environ["QQ_BOT_ID"]
SYSTEM_PROMPT_PATH = Path(__file__).parent / "prompt" / "system.txt"

def read_system_prompt() -> str:
    return SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")

def apply_system_prompt(system_prompt: str):
    temporary_path = SYSTEM_PROMPT_PATH.with_suffix(".txt.tmp")
    temporary_path.write_text(system_prompt, encoding="utf-8")
    temporary_path.replace(SYSTEM_PROMPT_PATH)
    set_system_prompt(system_prompt)

def initialize_system_prompt():
    cached_prompt = get_system_prompt()
    """
    if cached_prompt is None:
        set_system_prompt(read_system_prompt())
        return
    """
    apply_system_prompt(cached_prompt)

def handle_task(e: dict):
    def qq(e):
        print(f"QQ事件:{e['payload']}")
        if e['payload']['post_type']=="message":
            user_interface(e['payload'])
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
        h=get_recent_history(limit=16)
        messages = [
            {"role": "system", "content": system_prompt},
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
    
            
def user_interface(task: dict):
    res = None
    raw_message = task.get("raw_message", "")
    group_id = task.get("group_id")
    user_id = task.get("user_id")
    if not isinstance(raw_message, str):
        raw_message = ""

    if str(user_id) == TARGET_USER_ID and (not group_id or f'[CQ:at,qq={BOT_ID}]' in raw_message):
        if raw_message.startswith('/'):
            command_text = raw_message[1:].strip()
            if not command_text:
                return
            command_parts = command_text.split(maxsplit=1)
            cmd = command_parts[0]
            if cmd == 'dsB':
                balance = deepseekBalance()
                res = f"{balance}rmb" if balance is not None else "DeepSeek 余额查询失败"
            elif cmd == 'kmB':
                balance = kimiBalance()
                res = f"{balance}rmb" if balance is not None else "Kimi 余额查询失败"
            elif cmd == 'B':
                kimi_balance = kimiBalance()
                deepseek_balance = deepseekBalance()
                res = f'''余额
    kimi{kimi_balance if kimi_balance is not None else "查询失败"}rmb
    deepseek{deepseek_balance if deepseek_balance is not None else "查询失败"}rmb
    '''
            elif cmd == "search":
                query = command_parts[1].strip() if len(command_parts) > 1 else ""
                if not query:
                    return
                print(query)
                search_results = tavily_search(query)
                if search_results:
                    res = search_results[0].get('title', '')
                else:
                    res = "搜索无结果"
            # 将命令结果回复给用户（群消息回群，私聊回私聊）
            if res:
                if group_id:
                    send_group_msg(group_id, res)
                else:
                    send_private_msg(user_id, res)
            else:
                print("命令无结果:", raw_message)
        else:
            if not raw_message:
                print("空消息，跳过:", task)
                return

            print("收到任务:", task)

            e={
                "event_type":"active",
                "payload":{
                    "user_id":user_id,
                    "group_id":group_id,
                }
            }
            publish_to_queue(AGENT_QUEUE_NAME,e)


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