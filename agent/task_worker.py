# agent/task_worker.py
import os
import time
import traceback
from datetime import datetime, timezone
import json
from pathlib import Path
from workflow_parser import _read_workflow,parse_workflow

import tools.qq
import tools.bilibili

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
                        "content":raw_message
                    }
                }
                publish_to_queue(MAIN_AGENT_QUEUE_NAME,e)
    def terminal(e):
        e={
            "event_type":"workflow",
            "payload":{
                "content":e.get("payload",{}).get("message","")
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

    def setting(e):
        settings.update(e['payload'])
        write_settings_file(settings)
        set_settings(settings)

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
            insert_to_queue(MAIN_AGENT_QUEUE_NAME,e2)
            insert_to_queue(return_queue,e)
        else:
            insert_to_queue(return_queue,e)
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
                    "event_type":"tool_excute",
                    "payload":{'id':i['id'],
                        'tool':i['function']['name'],
                        "args":args
                    }
                }
                events.append(e)
            insert_to_queue(MAIN_AGENT_QUEUE_NAME,*events[::-1])

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

    def read_workflow_input(node, port_id):
        values = node.get('data_inputs', {}).get(port_id)
        if not isinstance(values, list) or len(values) <= 2:
            return False, None
        return True, values[-1]

    def propagate_workflow_output(workflow_map, node, port_id, value):
        for target_id, target_port in node.get('data_outputs', {}).get(port_id, []):
            target_values = workflow_map[target_id].get('data_inputs', {}).get(target_port)
            if not isinstance(target_values, list) or len(target_values) < 2:
                raise ValueError(
                    f"workflow target input is not connected: node {target_id}, port {target_port}"
                )
            target_values.append(value)

    def publish_workflow_node(workflow_map, endpoint):
        if endpoint is None:
            return
        target_id, target_port = endpoint
        event = {
            "event_type": f"workflow_{workflow_map[target_id]['type']}",
            "payload": {
                "workflow_map": workflow_map,
                "current_id": target_id,
            },
        }
        publish_to_queue(MAIN_AGENT_QUEUE_NAME, event)

    def publish_workflow_control_output(workflow_map, node, port_id='control-out'):
        publish_workflow_node(
            workflow_map,
            node.get('control_outputs', {}).get(port_id),
        )

    def workflow(e):
        workflow_map = parse_workflow(_read_workflow("main"))
        start = -1
        for i in range(len(workflow_map)):
            if workflow_map[i]["id"]=="input":
                start = i
        
        if start == -1:
            return 

        content = e['payload'].get("content")

        propagate_workflow_output(
            workflow_map, workflow_map[start], 'content-out', content
        )

        publish_workflow_node(
            workflow_map,
            workflow_map[start].get('control_outputs', {}).get('control-out'),
        )

    def workflow_llm(e):
        current_id=e['payload']['current_id']
        workflow_map=e['payload']['workflow_map']

        node = workflow_map[current_id]
        prompt = node['prompt']
        def message_order(port_id):
            return int(port_id.removeprefix('message-in-'))

        messages = []
        input_ports = sorted(
            (
                port_id
                for port_id in node['data_inputs']
                if port_id.startswith('message-in-')
                and port_id.removeprefix('message-in-').isdigit()
            ),
            key=message_order,
        )
        for port_id in input_ports:
            has_value, value = read_workflow_input(node, port_id)
            if has_value:
                messages.append(value)
        if prompt:
            messages.insert(0, {"role":"system", "content":prompt})
        print(messages)

        configured_tools = set(node.get("tools", []))
        tools = [
            schema
            for schema in registered_tools
            if schema["function"]["name"] in configured_tools
        ]
        content,reasoning,tool_calls=chat_with_deepseek(messages,tools=tools)

        propagate_workflow_output(workflow_map, node, 'output', content)
        if "reasoning" in node.get("data_outputs", {}):
            propagate_workflow_output(workflow_map, node, 'reasoning', reasoning)
        if "tool_calls" in node.get("data_outputs", {}):
            propagate_workflow_output(workflow_map, node, 'tool_calls', tool_calls)

        publish_workflow_control_output(workflow_map, node)

    def workflow_construct_message(e):
        current_id=e['payload']['current_id']
        workflow_map=e['payload']['workflow_map']
        node=workflow_map[current_id]
        has_content, content = read_workflow_input(node, 'content-in')
        if not has_content:
            return

        message = {"role":node.get("role", "user"), "content":content}
        propagate_workflow_output(workflow_map, node, 'message-out', message)

        publish_workflow_control_output(workflow_map, node)

    def workflow_construct_content(e):
        current_id = e['payload']['current_id']
        workflow_map = e['payload']['workflow_map']
        node = workflow_map[current_id]
        parts = []
        for item in node.get('append_items', []):
            if item.get('type') == 'fixed':
                parts.append(item.get('value', ''))
                continue
            has_value, value = read_workflow_input(node, item['port_id'])
            if has_value:
                parts.append(value if isinstance(value, str) else str(value))

        propagate_workflow_output(workflow_map, node, 'content-out', ''.join(parts))
        publish_workflow_control_output(workflow_map, node)

    def workflow_construct_list(e):
        current_id = e['payload']['current_id']
        workflow_map = e['payload']['workflow_map']
        node = workflow_map[current_id]
        init_values = []
        for port_id in node.get('data_inputs', {}):
            has_value, value = read_workflow_input(node, port_id)
            if has_value:
                init_values.append(value)

        propagate_workflow_output(workflow_map, node, 'list-out', init_values)

        publish_workflow_control_output(workflow_map, node)

    def workflow_foreach(e):
        current_id = e['payload']['current_id']
        workflow_map = e['payload']['workflow_map']
        node = workflow_map[current_id]
        has_items, items = read_workflow_input(node, 'list-in')
        if not has_items:
            return
        if not isinstance(items, list):
            raise ValueError(f"foreach input must be a list: node {node.get('id')}")
        if not items:
            publish_workflow_control_output(workflow_map, node)
            return

        propagate_workflow_output(
            workflow_map, node, 'item-out', items.pop(0)
        )
        publish_workflow_node(
            workflow_map,
            node.get('control_outputs', {}).get('loop-out'),
        )

    def workflow_router(e):
        current_id=e['payload']['current_id']
        workflow_map=e['payload']['workflow_map']


        node = workflow_map[current_id]
        has_key, key = read_workflow_input(node, 'content-in')
        if not has_key:
            return
        cases = {i['name']:i['successor'] for i in node['branches']}
        if key not in cases:
            return

        control_successors_id=cases.get(key)
        if control_successors_id is not None:
            publish_workflow_node(
                workflow_map,
                [control_successors_id, 'control-in'],
            )

    def workflow_tool(e):
        current_id=e['payload']['current_id']
        workflow_map=e['payload']['workflow_map']
        node=workflow_map[current_id]
        args = {}
        for parameter in node.get('parameters', []):
            has_value, value = read_workflow_input(node, parameter)
            if has_value:
                args[parameter] = value

        result=execute_tool(node['id'],node['tool'],args)
        propagate_workflow_output(workflow_map, node, 'output', result)

        publish_workflow_control_output(workflow_map, node)

    def workflow_tool_call(e):
        current_id = e['payload']['current_id']
        workflow_map = e['payload']['workflow_map']
        node = workflow_map[current_id]
        has_tool_call, tool_call = read_workflow_input(node, 'tool_call')
        if not has_tool_call:
            return
        if not isinstance(tool_call, dict):
            raise ValueError(f"tool_call input must be an object: node {node.get('id')}")

        tool_call_id = tool_call.get('id')
        function = tool_call.get('function')
        if not isinstance(tool_call_id, str) or not isinstance(function, dict):
            raise ValueError(f"tool_call input must use OpenAI tool call format: node {node.get('id')}")
        tool_name = function.get('name')
        arguments = function.get('arguments')
        if not isinstance(tool_name, str) or not isinstance(arguments, str):
            raise ValueError(f"tool_call function must contain name and raw arguments: node {node.get('id')}")

        try:
            args = json.loads(arguments)
            if not isinstance(args, dict):
                raise ValueError("tool arguments must be a JSON object")
            result = execute_tool(tool_call_id, tool_name, args)
        except (json.JSONDecodeError, TypeError, ValueError) as error:
            result = f"Error: 工具参数 JSON 解析失败: {error}"
        except Exception as error:
            result = f"Error: {error}"

        propagate_workflow_output(workflow_map, node, 'tool_call_id', tool_call_id)
        propagate_workflow_output(workflow_map, node, 'result', result)
        publish_workflow_control_output(workflow_map, node)

    handle_map = {
        "qq": qq,
        "terminal": terminal,
        "tool_excute": tool_excute,
        "tool_return": tool_return,
        "setting": setting,
        "active": active,
        "response": response,
        "rpc_review":rpc_review,
        "rpc_apply":rpc_apply,
        "workflow":workflow,
        "workflow_llm":workflow_llm,
        "workflow_construct_message":workflow_construct_message,
        "workflow_construct_content":workflow_construct_content,
        "workflow_construct_list":workflow_construct_list,
        "workflow_foreach":workflow_foreach,
        "workflow_router":workflow_router,
        "workflow_tool":workflow_tool,
        "workflow_tool_call":workflow_tool_call,
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