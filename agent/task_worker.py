# agent/task_worker.py
import os
import time
import traceback
from datetime import datetime, timezone
import json
from pathlib import Path
from bson import ObjectId
from pymongo import MongoClient
from pymongo.errors import PyMongoError
from workflow_parser import _read_workflow,parse_workflow
from workflow_validator import validate_workflow
from workflow_nodes import propagate_workflow_output, run_workflow_map

from history_repository import record_history,get_recent_history
from queue_client import (
    MAIN_AGENT_QUEUE_NAME,
    pop_from_queue,
    insert_to_queue,
    publish_to_queue,
    set_worker_status,
    set_settings,
    get_settings
)
from llm import chat_with_deepseek,openai_llm_api
from tools.tool import execute_tool, registered_tools
from tools.documents import system_documents_prompt


TARGET_USER_ID = os.environ["QQ_TARGET_USER_ID"]
BOT_ID = os.environ["QQ_BOT_ID"]
SETTINGS_PATH = Path(__file__).parent / "settings.json"


def read_active_workflow_id() -> str:
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
    try:
        with MongoClient(**mongo_kwargs) as client:
            setting = client[os.getenv("MONGO_DATABASE", "agent")][
                os.getenv("MONGO_SETTINGS_COLLECTION", "settings")
            ].find_one({"_id": "agent"}, {"workflow_id": 1})
    except PyMongoError as error:
        raise RuntimeError("failed to read active workflow setting") from error
    workflow_id = setting.get("workflow_id") if setting else None
    if not isinstance(workflow_id, ObjectId):
        raise RuntimeError("active workflow is not configured")
    return str(workflow_id)

def read_settings_file() -> dict:
    settings = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    return settings

def write_settings_file(settings):
    SETTINGS_PATH.write_text(json.dumps(settings,ensure_ascii=False),encoding="utf-8")

def initialize_settings():
    set_settings(read_settings_file())

def handle_task(e: dict):
    settings=get_settings()
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
                    "event_type":"workflow",
                    "payload":{
                        "content":raw_message,
                        "source":"qq",
                    }
                }
                publish_to_queue(MAIN_AGENT_QUEUE_NAME,e)
    def terminal(e):
        e={
            "event_type":"workflow",
            "payload":{
                "content":e.get("payload",{}).get("message",""),
                "source":"terminal",
            }
        }
        publish_to_queue(MAIN_AGENT_QUEUE_NAME,e)
    def tool_excute(e):
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
        insert_to_queue(MAIN_AGENT_QUEUE_NAME,r_e)

    def active(e):
        task_content=""
        return_queue = MAIN_AGENT_QUEUE_NAME
        if e.get("payload"):
            p = e.get("payload")
            task_content = p.get("task_content")
            # return_queue = p.get("return_queue")
        

        system_prompt = settings['system_prompt'].replace("{{TARGET_USER_ID}}", TARGET_USER_ID).replace("{{BOT_ID}}", BOT_ID)
        system_prompt = system_prompt.replace("{{SYSTEM_DOCUMENTS_PROMPT}}",system_documents_prompt())

        h=get_recent_history(limit=int(settings.get('max_context_count')))[::-1]
        messages = [
            {"role": "system", "content": system_prompt},
        ]

        context=[]

        for i in h:
            payload=i.get('payload')
            if i['event_type']=='qq':
                if i['payload']["post_type"]=="message":
                    if (not payload['group_id']) and str(payload['user_id']) == str(TARGET_USER_ID):
                        
                        context.append(f"<Command source='qq'>{payload['raw_message']}</Command>")
                    else:
                        #context.append(f"<QQ event='msg' type='group' group_id={payload['group_id']}  sender_id={payload['user_id']}>{payload['raw_message']}</QQ>")
                        pass
                #if i['payload']["post_type"]=="send" and str(i['payload']["target_id"]) == str(TARGET_USER_ID):
                #    context.append(f"<QQ event='msg' sender_id=self>{payload['raw_message']}</QQ>")

            if i['event_type']=='tool_return':
                context.append(f"""<tool>
<tool_name>{payload['tool']}</tool_name>
<tool_args>{json.dumps(payload['args'],ensure_ascii=False)}</tool_args>
<tool_result>{payload['result']}</tool_result>
</tool>""")
            if i['event_type']=='terminal':
                context.append(f"<Command source='terminal'>{payload['message']}</Command>")

            if i['event_type']=='response':
                if payload.get("content"):
                    context.append(f"<response target='terminal'>{payload['content']}</response>")

            if i['event_type']=='application':
                task_content=f"""<application>
                <sub_agent_name>{payload.get("sub_agent_name")}</sub_agent_name>
                <apply_tool_name>{payload.get("tool_name")}</apply_tool_name>
                <apply_tool_arguments>{payload.get("arguments")}</apply_tool_arguments>
                """
                context.append(task_content)
        messages.append({"role":"user","content":"\n".join(context)})

        if task_content:
            messages.append({"role":"user","content":task_content})

        # content,reasoning,tool_calls=openai_llm_api(messages,"Qwen3.8-27B-Q4_K_M-Uncensored","http://192.168.1.104:8200/v1","",extra={"thinking_budget_tokens":256,"max_completion_tokens":512+256})
        content,reasoning,tool_calls=chat_with_deepseek(messages)
        e={'event_type':"response",
        "payload":{
                "content":content,
                "reasoning":reasoning,
                "tool_calls":tool_calls
            }
        }
        if tool_calls:
            e2={
                    "event_type":"active",
                    "payload":{
                    }
                }
            insert_to_queue(MAIN_AGENT_QUEUE_NAME,e2)
            insert_to_queue(return_queue,e)
        else:
            insert_to_queue(return_queue,e)
    def tool_return(e):
        pass
    def response(e):
        pass

    def rpc_review(e):
        pass

    def rpc_apply(e):
        p=e.get('payload')
        if not p:
            return
        tool_name=p.get("tool_name")
        tool_arguments=p.get("tool_arguments")
        subagent_name=p.get("subagent_name")
        callback_queue_name=p.get("callback_queue_name")
        e = {
            "event_type":"rpc_review",
            "subagent_name":subagent_name,
            "callback_queue_name":callback_queue_name,
            "tool_name":tool_name,
            "tool_arguments":tool_arguments
        }
        publish_to_queue(MAIN_AGENT_QUEUE_NAME,e)

    def workflow(e):
        active_workflow_id = read_active_workflow_id()
        workflow_document = _read_workflow(active_workflow_id, by_id=True)
        validate_workflow(workflow_document)
        workflow_map = parse_workflow(workflow_document)
        for node in workflow_map:
            node['_workflow_call_stack'] = [workflow_document['name']]
        
        start = next(
            (
                index
                for index, node in enumerate(workflow_map)
                if node["type"] == "input"
            ),
            None,
        )
        if start is None:
            raise ValueError("workflow has no input node")

        input_node = workflow_map[start]
        workflow_ports = input_node.get('workflowPorts', [])
        for port in workflow_ports:
            propagate_workflow_output(
                workflow_map, input_node, port['id'], e['payload'].get(port['name'])
            )

        output = run_workflow_map(workflow_map, start)
        publish_to_queue(MAIN_AGENT_QUEUE_NAME, {
            "event_type": "response",
            "payload": {"content": output.get("content", output)},
        })

    handle_map = {
        "qq": qq,
        "terminal": terminal,
        "tool_excute": tool_excute,
        "tool_return": tool_return,
        "active": active,
        "response": response,
        "rpc_review":rpc_review,
        "rpc_apply":rpc_apply,
        "workflow":workflow,
    }

    record_history(e)
    handler = handle_map.get(e['event_type'])
    handler(e)
    

def main():
    print("Agent worker started...")
    initialize_settings()
    while True:
        try:
            set_worker_status({
                "state": "idle",
                "updated_at": datetime.now(timezone.utc).isoformat(),
            })
            task = pop_from_queue(MAIN_AGENT_QUEUE_NAME, timeout=5)
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