"""Runtime workflow compilation and process/terminal initialization."""
import json
import secrets
from datetime import datetime, timezone
from uuid import uuid4

from process import WorkflowProcess, TerminalProcess
from process_permissions import snapshot_process_permissions


def initialize_process_pair(process: WorkflowProcess) -> TerminalProcess:
    now = datetime.now(timezone.utc).isoformat()
    process.process_type = "workflow"
    process.root_process_id = process.root_process_id or process.process_id
    process.invocation_id = process.invocation_id or process.process_id
    process.start_time = now
    process.status = "ready"
    process.wait_for = None
    process.terminal_process_id = uuid4().hex

    terminal_process = TerminalProcess(
        process_id=process.terminal_process_id,
        process_type="terminal",
        parent_process_id=process.process_id,
        root_process_id=process.root_process_id,
        workflow_name=process.workflow_name,
        terminal_id=process.terminal_id,
        start_time=now,
        status="waiting_for_input",
        wait_for={"kind": "terminal_message"},
    )

    process.record_event("created")
    terminal_process.record_event("created")
    return terminal_process


def build_workflow_process(
    document: dict,
    inputs: dict,
    file_id: str,
    file_name: str,
    terminal_id: str,
    permissions: dict | None = None,
) -> WorkflowProcess:
    from workflow_nodes import propagate_workflow_output, workflow_execution_timeout_ms
    from workflow_parser import parse_workflow
    from workflow_structs import validate_struct_definitions, validate_value
    from workflow_validator import validate_workflow

    process_permissions = snapshot_process_permissions(permissions)

    if not isinstance(file_name, str) or not file_name.strip():
        raise ValueError("工作流文件名不能为空")
    if not isinstance(terminal_id, str) or not terminal_id.strip():
        raise ValueError("terminal_id must be a non-empty string")
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
    return WorkflowProcess(
        process_id=uuid4().hex,
        process_type="workflow",
        status="ready",
        parent_process_id="user_interface",
        workflow_file_id=file_id,
        permissions=process_permissions,
        _workspace_token=secrets.token_urlsafe(32),
        workflow_name=file_name,
        execution_timeout_ms=workflow_execution_timeout_ms(document),
        workflow_file=file_name,
        call_stack=[file_name],
        input=input_values,
        workflow=json.dumps(workflow, ensure_ascii=False, allow_nan=False),
        current_node_id=-1,
        terminal_id=terminal_id,
    )
