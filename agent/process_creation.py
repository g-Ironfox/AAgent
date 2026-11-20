"""Runtime workflow compilation and process/terminal initialization."""
import json
from datetime import datetime, timezone
from uuid import uuid4

from process_repository import record_process_event


def initialize_process_pair(process: dict) -> dict:
    """Initialize the supplied workflow process and return its passive terminal."""
    if not isinstance(process, dict):
        raise ValueError('process must be a dictionary')
    process_id = process.get('process_id')
    if not isinstance(process_id, str) or not process_id:
        raise ValueError('process_id must be a non-empty string')
    now = datetime.now(timezone.utc).isoformat()
    terminal_id = process.get('terminal_id')
    if not isinstance(terminal_id, str) or not terminal_id.strip():
        raise ValueError('terminal_id must be a non-empty string')
    terminal_process_id = uuid4().hex
    process['process_type'] = 'workflow'
    process.setdefault('root_process_id', process_id)
    process.setdefault('invocation_id', process_id)
    process.setdefault('ancestor_invocation_ids', [])
    process.setdefault('context_ids', [])
    process.setdefault('active_duration_ms', 0)
    process.setdefault('node_trace', [])
    process.setdefault('pending_call', None)
    process['start_time'] = now
    process['status'] = 'ready'
    process['wait_for'] = None
    process['terminal_process_id'] = terminal_process_id
    process['terminal_id'] = terminal_id

    terminal_process = {
        'process_id': terminal_process_id,
        'process_type': 'terminal',
        'parent_process_id': process_id,
        'root_process_id': process['root_process_id'],
        'workflow_name': process.get('workflow_name'),
        'terminal_id': terminal_id,
        'start_time': now,
        'status': 'waiting_for_input',
        'wait_for': {'kind': 'terminal_message'},
    }

    record_process_event(process, 'created')
    record_process_event(terminal_process, 'created')
    return terminal_process


def build_workflow_process(
    document: dict,
    inputs: dict,
    file_id: str,
    file_name: str,
    terminal_id: str,
) -> dict:
    from workflow_nodes import propagate_workflow_output
    from workflow_parser import parse_workflow
    from workflow_structs import validate_struct_definitions, validate_value
    from workflow_validator import validate_workflow

    from workflow_contract import migrate_subprocess_workflow_format

    if not isinstance(file_name, str) or not file_name.strip():
        raise ValueError("工作流文件名不能为空")
    if not isinstance(terminal_id, str) or not terminal_id.strip():
        raise ValueError("terminal_id must be a non-empty string")
    document = migrate_subprocess_workflow_format(document)
    validate_workflow(document)
    ports = document["input_ports"]
    unknown = set(inputs) - {port["name"] for port in ports}
    if unknown:
        raise ValueError("未知的工作流输入参数: " + ", ".join(sorted(unknown)))
    definitions = validate_struct_definitions(document.get("metadata", {}).get("structs", []))
    for port in ports:
        if inputs.get(port["name"]) is not None:
            validate_value(port["type"], inputs[port["name"]], definitions)
    workflow = parse_workflow(document)
    start = next((i for i, node in enumerate(workflow) if node["type"] == "input"), None)
    if start is None:
        raise ValueError("工作流缺少 input 节点")
    for node in workflow:
        node["_workflow_call_stack"] = [file_name]
    input_node = workflow[start]
    input_values = {}
    for port in input_node.get("workflowPorts", []):
        value = inputs.get(port["name"])
        input_values[port["name"]] = value
        propagate_workflow_output(workflow, input_node, port["id"], value)
    return {
        "process_id": uuid4().hex,
        "parent_process_id": "user_interface",
        "workflow_file_id": file_id,
        "workflow_name": file_name,
        "workflow_file": file_name,
        "call_stack": [file_name],
        "input": input_values,
        "workflow": json.dumps(workflow, ensure_ascii=False, allow_nan=False),
        "current_node_id": -1,
        "control_port": None,
        "terminal_id": terminal_id,
    }
