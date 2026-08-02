# agent/task_worker.py
import os
import time
import traceback
from datetime import datetime, timezone
import json

from history_repository import record_history,get_recent_history
from queue_client import (
    AGENT_QUEUE_NAME,
    pop_from_queue,
    insert_to_queue,
    publish_to_queue,
    set_worker_status,
)
from llm import chat_with_deepseek
from qqapi import send_group_msg, send_private_msg
from tool import execute_tool, deepseekBalance, kimiBalance, tavily_search

TARGET_USER_ID = os.environ["QQ_TARGET_USER_ID"]
BOT_ID = os.environ["QQ_BOT_ID"]

def handle_task(e: dict):
    record_history(e)
    if e['event_type'] == "qq":
        print(f"QQ事件:{e['payload']}")
        if e['payload']['post_type']=="message":
            user_interface(e['payload'])
    elif e['event_type'] == "terminal":
        e={
            "event_type":"active",
            "payload":{
            }
        }
        publish_to_queue(AGENT_QUEUE_NAME,e)
        
    elif e['event_type'] == 'tool':
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

    elif e["event_type"]=="tool_return":
        pass
    elif e["event_type"]=="active":

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
            if i['event_type']=='terminal':
                messages.append({"role":"user",'content':f"<Command>{payload['message']}</Command>"})

            if i['event_type']=='response':
                messages.append({"role":"assistant","content":payload["content"] or ""})

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
    elif e["event_type"]=="response":
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
            
def user_interface(task: dict):
    res = None
    raw_message = task.get("raw_message", "")
    group_id = task.get("group_id")
    user_id = task.get("user_id")
    if not isinstance(raw_message, str):
        raw_message = ""

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

        if str(user_id) == TARGET_USER_ID and (not group_id or f'[CQ:at,qq={BOT_ID}]' in raw_message):
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