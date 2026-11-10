# agent/task_worker.py
import os
import time
import traceback
from datetime import datetime, timezone
from pymongo import MongoClient
from pymongo.errors import PyMongoError
from workflow_parser import WorkflowParseError, _read_workflow, _read_workspace_workflow, parse_workflow
from workflow_validator import validate_workflow
from workflow_nodes import propagate_workflow_output, run_workflow_map

from history_repository import record_history
from queue_client import (
    MAIN_AGENT_QUEUE_NAME,
    pop_from_queue,
    publish_to_queue,
    set_worker_status,
)

EVENT_VERSION = "1.1"


def validate_event_version(event: dict) -> None:
    version = event.get("version")
    if version != EVENT_VERSION:
        raise ValueError(
            f"unsupported event version: {version!r}; expected {EVENT_VERSION}"
        )


def read_bound_workflow(event_type: str) -> dict[str, str] | None:
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
            database = client[os.getenv("MONGO_DATABASE", "agent")]
            binding = database[os.getenv("MONGO_EVENT_BINDING_COLLECTION", "event_bindings")].find_one(
                {"event_type": event_type, "enabled": True}, {"workflow_file_id": 1, "workflow_name": 1}
            )
    except PyMongoError as error:
        raise RuntimeError("failed to read event binding") from error
    if binding is None:
        return None
    if binding.get("workflow_file_id"):
        return {"workflow_file_id": binding["workflow_file_id"]}
    if binding.get("workflow_name"):
        return {"workflow_name": binding["workflow_name"]}
    raise RuntimeError("event binding has no workflow target")


def handle_task(e: dict):
    validate_event_version(e)
    record_history(e)
    event_type = e["event_type"]
    if event_type != "workflow":
        workflow_target = read_bound_workflow(event_type)
        if workflow_target is not None:
            payload = {
                key: value
                for key, value in e["payload"].items()
                if key not in {"origin", "workflow_file_id", "workflow_name"}
            }
            payload.update(workflow_target, origin=e)
            publish_to_queue(MAIN_AGENT_QUEUE_NAME, {
                "event_type": "workflow",
                "payload": payload,
            })
        return

    payload = e["payload"]
    target_key = "workflow_file_id" if payload.get("workflow_file_id") else "workflow_name"
    workflow_target = payload[target_key]
    try:
        workflow_document = (
            _read_workspace_workflow(workflow_target)
            if target_key == "workflow_file_id"
            else _read_workflow(workflow_target)
        )
    except WorkflowParseError as error:
        if not str(error).startswith(("workflow not found:", "workflow file not found:")):
            raise
        publish_to_queue(MAIN_AGENT_QUEUE_NAME, {
            "event_type": "error",
            "payload": {target_key: workflow_target, "message": "workflow not found"},
        })
        return
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
    origin = e['payload'].get('origin', e)
    for port in workflow_ports:
        value = origin if port['name'] == 'origin' else e['payload'].get(port['name'])
        propagate_workflow_output(
            workflow_map, input_node, port['id'], value
        )

    output = run_workflow_map(workflow_map, start)
    publish_to_queue(MAIN_AGENT_QUEUE_NAME, {
        "event_type": "response",
        "payload": {"content": output.get("content", output)},
    })
    

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
            except Exception as error:
                if task.get("event_type") != "error":
                    payload = {"message": str(error)}
                    for key in ("workflow_file_id", "workflow_name"):
                        target = task.get("payload", {}).get(key)
                        if target is not None:
                            payload[key] = target
                    publish_to_queue(MAIN_AGENT_QUEUE_NAME, {
                        "event_type": "error",
                        "payload": payload,
                    })
                raise
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