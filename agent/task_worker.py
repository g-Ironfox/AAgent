# agent/task_worker.py
import os
import time
import traceback
from datetime import datetime, timezone
from bson import ObjectId
from pymongo import MongoClient
from pymongo.errors import PyMongoError
from workflow_parser import _read_workflow,parse_workflow
from workflow_validator import validate_workflow
from workflow_nodes import propagate_workflow_output, run_workflow_map

from history_repository import record_history
from queue_client import (
    MAIN_AGENT_QUEUE_NAME,
    pop_from_queue,
    publish_to_queue,
    set_worker_status,
)


TARGET_USER_ID = os.environ["QQ_TARGET_USER_ID"]
BOT_ID = os.environ["QQ_BOT_ID"]


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
                "content":e.get("payload",{}).get("content",""),
                "source":"terminal",
            }
        }
        publish_to_queue(MAIN_AGENT_QUEUE_NAME,e)
    def response(e):
        del e

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
        "response": response,
        "workflow":workflow,
    }

    record_history(e)
    handler = handle_map.get(e['event_type'])
    handler(e)
    

def main():
    print("Agent worker started...")
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