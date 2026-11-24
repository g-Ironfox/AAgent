import copy
import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4
from process_creation import initialize_process_pair

from pymongo import ASCENDING, MongoClient
from pymongo.errors import PyMongoError

from redis_client import get_connection, get_event_connection
from scheduler_projection import queue_public_process_updates, rebuild_public_scheduler
from process import Process, WorkflowProcess
from process_repository import (
    BLOCKED_PROCESSES, EXTERNAL_EVENTS, PROCESSTABLE, READY_PROCESSES,
    enqueue_terminal_input,
    claim_process, commit_execution_slice, spawn_child_and_suspend_parent,
    publish_process_pair, terminate_process_tree,
    kill_process_tree,
    TERMINAL_STATUSES, wake_process as wake_process_record,
)
from workflow_nodes import (
    WORKFLOW_END, WorkflowStep, FunctionCall, current_workflow_process,
    execute_node, propagate_workflow_output, read_workflow_input,
)
from terminal_repository import terminal_process_context

MONGO_HOST = os.getenv('MONGO_HOST', 'mongodb')
MONGO_PORT = int(os.getenv('MONGO_PORT', '27017'))
MONGO_DATABASE = os.getenv('MONGO_DATABASE', 'agent')
MONGO_PROCESS_LOG_COLLECTION = os.getenv(
    'MONGO_PROCESS_LOG_COLLECTION', 'process_logs'
)
MONGO_USER = os.getenv('MONGO_USER')
MONGO_PASS = os.getenv('MONGO_PASS', '')

_mongo_client = None
_process_log_collection = None
logger = logging.getLogger(__name__)
SCHEDULER_TIME_SLICE_MS = 500


def _get_process_log_collection():
    global _mongo_client, _process_log_collection
    if _process_log_collection is None:
        options: dict[str, Any] = {
            'host': MONGO_HOST,
            'port': MONGO_PORT,
            'serverSelectionTimeoutMS': 5000,
            'tz_aware': True,
        }
        if MONGO_USER:
            options.update(username=MONGO_USER, password=MONGO_PASS, authSource='admin')
        _mongo_client = MongoClient(**options)
        _process_log_collection = _mongo_client[MONGO_DATABASE][
            MONGO_PROCESS_LOG_COLLECTION
        ]
        _process_log_collection.create_index(
            [('process_id', ASCENDING)], unique=True, name='process_id_unique'
        )
    return _process_log_collection


def _parse_start_time(value: str) -> datetime:
    try:
        start_time = datetime.fromisoformat(value)
    except (TypeError, ValueError) as error:
        raise ValueError('process start_time must be an ISO datetime') from error
    if start_time.tzinfo is None:
        raise ValueError('process start_time must include a timezone')
    return start_time.astimezone(timezone.utc)


def _initialize_process_timing(process: WorkflowProcess) -> None:
    _sync_process_observability(process)
    _sync_related_process_logs(process.terminal_process_id)


def read_process(process_id: str) -> Process:
    """Read PROCESSTABLE[process_id], stored as a JSON object in a Redis hash."""
    if not isinstance(process_id, str) or not process_id:
        raise ValueError('process_id must be a non-empty string')
    raw = get_connection().hget(PROCESSTABLE, process_id)
    if raw is None:
        raise KeyError(f'process not found: {process_id}')
    try:
        process = json.loads(raw)
    except (TypeError, ValueError) as error:
        raise ValueError(f'invalid process data: {process_id}') from error
    process = Process.from_record(process)
    if process.process_id != process_id:
        raise ValueError(f'invalid process data: {process_id}')
    return process


def write_process(process: Process) -> bool:
    """Replace a complete process JSON record, keyed by process_id."""
    process_id = process.process_id
    try:
        raw = json.dumps(process.to_record(), ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as error:
        raise ValueError(f'process data is not JSON serializable: {process_id}') from error
    with get_connection().pipeline(transaction=True) as pipe:
        pipe.hset(PROCESSTABLE, process_id, raw)
        queue_public_process_updates(pipe, {process_id: process}, enqueue_ready=False)
        pipe.execute()
    return True


def create_process(process: WorkflowProcess) -> WorkflowProcess:
    """创建 root workflow 与 mailbox，并发布初始调度和 terminal 状态。"""
    terminal_process = initialize_process_pair(process)

    publish_process_pair(get_connection(), process, terminal_process)
    _initialize_process_timing(process)
    return process


def handle_external_event(client, raw_event: str) -> None:
    """Apply one external command inside the runtime ownership boundary."""
    try:
        event = json.loads(raw_event)
        if not isinstance(event, dict):
            raise ValueError("external event must be an object")
        event_type = event.get("type")
        if event_type == "create_process":
            from process_creation import build_workflow_process

            content = event["workflow_content"]
            document = json.loads(content) if isinstance(content, str) else content
            process = build_workflow_process(
                document,
                event.get("inputs", {}),
                event["workflow_file_id"],
                event["workflow_name"],
                event["terminal_id"],
                event.get("workflow_permissions"),
            )
            create_process(process)
            return
        if event_type == "terminal_message":
            owner = enqueue_terminal_input(client, event["terminal_id"], event["content"])
            if owner is not None:
                _sync_process_observability(owner)
            return
        if event_type == "kill_process":
            kill_process(event["process_id"])
            return
        raise ValueError(f"unsupported external event type: {event_type!r}")
    except (KeyError, TypeError, ValueError) as error:
        logger.warning("discarding invalid external event: %s", error)
    except Exception:
        logger.exception("failed to handle external event")


def drain_external_events(client, event_client) -> int:
    """Read public events and apply their effects to the kernel client."""
    handled = 0
    while True:
        raw_event = event_client.rpop(EXTERNAL_EVENTS)
        if raw_event is None:
            return handled
        handle_external_event(client, raw_event)
        handled += 1


def block_process(process_id: str, wait_for: dict) -> Process:
    """Block a workflow process until a referenced process emits an event."""
    if (
        not isinstance(wait_for, dict)
        or wait_for.get('kind') not in {'process_exit', 'terminal_message'}
        or not isinstance(wait_for.get('process_id'), str)
        or not wait_for['process_id']
    ):
        raise ValueError(
            "wait_for must identify a process_exit or terminal_message source process"
        )
    process = read_process(process_id)
    process.block(wait_for)
    process.record_event('blocked', wait_for=wait_for)
    write_process(process)
    client = get_connection()
    client.lrem(READY_PROCESSES, 0, process_id)
    client.sadd(BLOCKED_PROCESSES, process_id)
    _sync_process_observability(process)
    return process


def wake_process(process_id: str, source_process_id: str, event_kind: str) -> Process:
    """Wake a process only when the source process and event kind both match."""
    process = wake_process_record(
        get_connection(), process_id, source_process_id, event_kind
    )
    _sync_process_observability(process)
    return process


def _sync_process_observability(process: Process) -> None:
    """Redis is authoritative; observability failures never change execution state."""
    try:
        node_trace = copy.deepcopy(process.node_trace)
        for entry in node_trace:
            for field in ('started_at', 'finished_at'):
                if entry.get(field):
                    entry[field] = _parse_start_time(entry[field])
        fields = {
            'status': process.status,
            'process_type': process.process_type,
            'terminal_id': process.terminal_id,
            'terminal_process_id': process.terminal_process_id,
            'invocation_id': process.invocation_id,
            'call_stack': copy.deepcopy(process.call_stack),
            'wait_for': process.wait_for,
            'events': copy.deepcopy(process.events),
            'input': process.input,
            'output': process.result,
            'parent_process_id': process.parent_process_id,
            'root_process_id': process.root_process_id,
            'workflow_name': process.workflow_name,
            'nodes': node_trace,
            'active_duration_ms': process.active_duration_ms,
            'observed_at': datetime.now(timezone.utc),
            'current_node_id': process.current_node_id,
        }
        if process.finished_at:
            finished_at = _parse_start_time(process.finished_at)
            fields.update(
                finished_at=finished_at,
                total_duration_ms=round((finished_at - _parse_start_time(process.start_time)).total_seconds() * 1000),
                error=process.error,
            )
        _get_process_log_collection().update_one(
            {'process_id': process.process_id},
            {'$setOnInsert': {
                'process_id': process.process_id,
                'start_time': _parse_start_time(process.start_time),
            }, '$set': fields}, upsert=True,
        )
        if (process.process_type == 'workflow'
                and process.status in TERMINAL_STATUSES and process.workflow_name):
            from workflow_run_repository import record_process_workflow_run
            record_process_workflow_run({
                'run_id': process.invocation_id,
                'process_id': process.process_id,
                'parent_process_id': process.parent_process_id,
                'root_process_id': process.root_process_id,
                'workflow_name': process.workflow_name,
                'call_stack': process.call_stack,
                'started_at': _parse_start_time(process.start_time),
                'finished_at': _parse_start_time(process.finished_at),
                'duration_ms': fields['total_duration_ms'],
                'active_duration_ms': process.active_duration_ms,
                'status': process.status,
                'input': process.input,
                'output': process.result,
                'node_trace': process.node_trace,
                'error': process.error,
            })
    except Exception:
        logger.exception('failed to record process observations for %s', process.process_id)


def _sync_related_process_logs(*process_ids: str | None) -> None:
    for process_id in dict.fromkeys(process_ids):
        if not process_id:
            continue
        try:
            _sync_process_observability(read_process(process_id))
        except KeyError:
            # Root callers can be external identities rather than kernel processes.
            continue
        except Exception:
            logger.exception('failed to read process for logging: %s', process_id)


def _cleanup_process_contexts(process: WorkflowProcess) -> None:
    from workflow_context_repository import delete_contexts
    try:
        delete_contexts(set(process.context_ids))
    except Exception:
        logger.exception('failed to clean up process Contexts: %s', process.process_id)


def terminate_process(process_id: str) -> Process:
    changed = terminate_process_tree(get_connection(), process_id)
    for process in changed:
        if process.process_type == 'workflow':
            _cleanup_process_contexts(process)
        _sync_process_observability(process)
    process = read_process(process_id)
    _sync_related_process_logs(process.parent_process_id)
    return process


def kill_process(process_id: str) -> Process:
    changed = kill_process_tree(get_connection(), process_id)
    for process in changed:
        if process.process_type == 'workflow':
            _cleanup_process_contexts(process)
        _sync_process_observability(process)
    return read_process(process_id)


def _resume_subprocess(process: WorkflowProcess, workflow_map: list[dict]) -> None:
    """把已结束 child 的结果或错误写回父图，并清除 pending call。"""
    pending = process.pending_call
    if not pending:
        return
    child = read_process(pending['child_process_id'])
    if child.parent_process_id != process.process_id:
        raise ValueError('child process has an invalid parent link')
    node = workflow_map[pending['node_index']]
    if node.get('id') != pending['node_id'] or node.get('type') != "spawn_and_wait_subprocess":
        raise ValueError('pending child call does not match spawn_and_wait_subprocess node')
    status = child.status
    if status != 'completed':
        error = child.error or (
            'child was terminated' if status == 'terminated' else 'child did not complete successfully'
        )
        message = f"subprocess {child.workflow_name} ({child.process_id}) {status}: {error}"
        if status not in {'failed', 'terminated'} or 'error' not in node.get('successors', {}):
            raise ValueError(message)
        details = {
            'workflow_file': child.workflow_file or child.workflow_name,
            'process_id': child.process_id,
            'status': status,
            'error': error,
        }
        error_json = json.dumps(details, ensure_ascii=False, allow_nan=False, separators=(',', ':'))
        propagate_workflow_output(workflow_map, node, 'error-json', error_json)
        _finish_call_trace(process, 'failed', message)
        process.current_node_id = pending['node_index']
        process.control_port = 'error'
        process.pending_call = None
        return
    result = child.result
    if not isinstance(result, dict):
        raise ValueError('subprocess result must be an object')
    from workflow_structs import validate_value
    child_map = json.loads(child.workflow)
    output_node = next(node for node in child_map if node.get('type') == 'output')
    ports = {port['name']: port for port in output_node.get('workflowPorts', [])}
    if result.keys() - ports.keys():
        raise ValueError('subprocess returned undeclared output')
    for name, value in result.items():
        validate_value(ports[name]['type'], value, {})
    result_json = json.dumps(result, ensure_ascii=False, allow_nan=False, separators=(',', ':'))
    propagate_workflow_output(workflow_map, node, 'result-json', result_json)
    _finish_call_trace(process, 'completed')
    process.current_node_id = pending['node_index']
    process.control_port = 'next'
    process.pending_call = None


def _finish_call_trace(process: WorkflowProcess, status: str, error: str | None = None) -> None:
    pending = process.pending_call
    if not pending:
        return
    trace = process.node_trace[pending['trace_index']]
    now = datetime.now(timezone.utc)
    trace.update(status=status, finished_at=now.isoformat())
    trace['elapsed_ms'] = round((now - _parse_start_time(trace['started_at'])).total_seconds() * 1000)
    if error:
        trace['error'] = error


def _next_process_node(process: Process, workflow_map: list[dict]) -> int:
    """Resolve the next node from the last completed node and selected port."""
    completed_id = process.current_node_id
    if isinstance(completed_id, bool) or not isinstance(completed_id, int):
        raise ValueError('invalid current_node_id')
    if completed_id == WORKFLOW_END:
        kind = 'function_input' if process.active_function_id else 'input'
        current_id = next((i for i, node in enumerate(workflow_map)
                           if node.get('type') == kind
                           and node.get('function_id') == process.active_function_id), None)
    elif 0 <= completed_id < len(workflow_map):
        current_id = workflow_map[completed_id].get('successors', {}).get(process.control_port)
    else:
        raise ValueError('invalid current_node_id')
    if (isinstance(current_id, bool) or not isinstance(current_id, int)
            or not 0 <= current_id < len(workflow_map)):
        raise ValueError('invalid or disconnected workflow successor')
    return current_id


def _function_template(workflow_map: list[dict]) -> list[dict]:
    """Copy graph definitions without copying any invocation's mutable state."""
    template = copy.deepcopy(workflow_map)
    static_fields = {'_struct_definitions', '_tool_kind', '_metadata_tools', '_function_name'}
    for node in template:
        for key in list(node):
            if key.startswith('_') and key not in static_fields:
                node.pop(key)
        for slot in node.get('data_inputs', {}).values():
            slot[2] = None
    return template


def _push_function(process: WorkflowProcess, workflow_map: list[dict], current_id: int, target: str) -> list[dict]:
    from workflow_structs import validate_value

    stack = process.function_stack
    if len(stack) >= 64:
        raise ValueError('function call depth exceeds 64')
    if process.function_template is None:
        process.function_template = _function_template(workflow_map)
    child_map = copy.deepcopy(process.function_template)
    entry = next((node for node in child_map if node['type'] == 'function_input'
                  and node.get('function_id') == target), None)
    if entry is None:
        raise ValueError(f'function input not found: {target}')
    caller = workflow_map[current_id]
    for port in entry.get('function_ports', []):
        port_id = f"function:{port['name']}"
        present, value = read_workflow_input(caller, port_id)
        if not present:
            raise ValueError(f'function argument is missing: {target}.{port["name"]}')
        validate_value(port['type'], value, entry.get('_struct_definitions', {}))
        propagate_workflow_output(child_map, entry, port_id, value)
    stack.append({'workflow': workflow_map, 'current_node_id': current_id,
                  'control_port': 'next', 'function_id': process.active_function_id,
                  'function_name': process.active_function_name,
                  'function_call_id': process.active_function_call_id})
    process.active_function_id = target
    process.active_function_name = entry.get('_function_name') or target
    process.active_function_call_id = uuid4().hex
    process.current_node_id = WORKFLOW_END
    process.control_port = None
    return child_map


def _pop_function(process: WorkflowProcess, node: dict) -> list[dict]:
    frame = process.function_stack.pop()
    parent_map = frame['workflow']
    caller = parent_map[frame['current_node_id']]
    for name, value in node.pop('_workflow_result', {}).items():
        propagate_workflow_output(parent_map, caller, f'function:{name}', value)
    process.current_node_id = frame['current_node_id']
    process.control_port = frame['control_port']
    process.active_function_id = frame['function_id']
    process.active_function_name = frame.get('function_name')
    process.active_function_call_id = frame.get('function_call_id')
    return parent_map


def Executor(process_id: str) -> Process:
    """claim 并运行一个时间片，再按普通提交或 spawn 生命周期原子落库。"""
    from workflow_context_repository import current_persistent_invocation_id

    client = get_connection()
    process, claimed = claim_process(client, process_id)
    if not claimed:
        return process
    _sync_process_observability(process)
    workflow_map = []
    context_ids = set(process.context_ids)
    child = child_terminal = None
    trace = None
    trace_pending = False
    started = time.perf_counter()
    process_token = current_workflow_process.set(process)
    context_token = current_persistent_invocation_id.set(process.invocation_id)
    try:
        _parse_start_time(process.start_time)
        workflow_map = json.loads(process.workflow)
        if not isinstance(workflow_map, list) or not all(isinstance(node, dict) for node in workflow_map):
            raise ValueError(f'invalid workflow data: {process_id}')
        timeout_ms = process.execution_timeout_ms
        timeout_seconds = timeout_ms / 1000 if timeout_ms is not None else None
        _resume_subprocess(process, workflow_map)
        current_id = _next_process_node(process, workflow_map)
        def bind_runtime_context(graph):
            for graph_node in graph:
                graph_node['_workflow_invocation_id'] = process.invocation_id
                graph_node['_workflow_ancestor_invocation_ids'] = process.ancestor_invocation_ids
                graph_node['_workflow_context_ids'] = context_ids
                graph_node['_workflow_call_stack'] = process.call_stack

        bind_runtime_context(workflow_map)
        while process.status == 'running' or process.status == 'ready':
            elapsed_ms = (time.perf_counter() - started) * 1000
            if timeout_ms is not None and process.active_duration_ms + elapsed_ms >= timeout_ms:
                raise TimeoutError(
                    f'workflow execution exceeded {timeout_seconds:g} seconds of active execution'
                )
            node = workflow_map[current_id]
            node_started = time.perf_counter()
            trace = {
                'index': len(process.node_trace) + 1,
                'node_id': node.get('id'), 'node_name': node.get('name'),
                'node_type': node.get('type'),
                'started_at': datetime.now(timezone.utc).isoformat(),
                'status': 'completed',
            }
            trace_pending = True
            if process.active_function_id:
                if not process.active_function_call_id:
                    process.active_function_call_id = uuid4().hex
                trace.update(
                    function_id=process.active_function_id,
                    function_name=process.active_function_name or process.active_function_id,
                    function_call_id=process.active_function_call_id,
                    function_depth=len(process.function_stack),
                )
            with terminal_process_context(
                process.terminal_process_id,
                process.terminal_id,
            ):
                outcome = execute_node(current_id, workflow_map)
            handled_error = node.pop('_handled_subprocess_error', None)
            if handled_error is not None:
                trace.update(status='failed', error=handled_error)
            elapsed_ms = (time.perf_counter() - started) * 1000
            if timeout_ms is not None and process.active_duration_ms + elapsed_ms > timeout_ms:
                raise TimeoutError(
                    f'workflow execution exceeded {timeout_seconds:g} seconds of active execution'
                )
            process.mark_ready()
            if isinstance(outcome, FunctionCall):
                workflow_map = _push_function(process, workflow_map, current_id, outcome.function_id)
                bind_runtime_context(workflow_map)
                current_id = _next_process_node(process, workflow_map)
            elif isinstance(outcome, WorkflowStep):
                process.block(outcome.wait_for)
                child = outcome.child_process
                if child is not None:
                    child_terminal = initialize_process_pair(child)
                    process.pending_call = {
                        'node_id': node['id'], 'node_index': current_id,
                        'child_process_id': child.process_id,
                        'trace_index': len(process.node_trace),
                    }
                    trace.update(status='waiting', child_process_id=child.process_id)
                else:
                    trace['status'] = 'waiting'
            else:
                process.current_node_id = current_id
                process.control_port = node.get('_selected_control_port')
                if outcome == WORKFLOW_END:
                    if node.get('type') == 'function_output':
                        if not process.function_stack:
                            raise ValueError('function output has no caller')
                        workflow_map = _pop_function(process, node)
                        # Persisted caller frames have no runtime bindings.
                        bind_runtime_context(workflow_map)
                    else:
                        process.finish('completed', record_event=False)
                        process.result = node.pop('_workflow_result', {})
                if process.status == 'ready':
                    current_id = _next_process_node(process, workflow_map)
            trace['duration_ms'] = round((time.perf_counter() - node_started) * 1000)
            if trace['status'] != 'waiting':
                trace['finished_at'] = datetime.now(timezone.utc).isoformat()
            process.node_trace.append(trace)
            trace_pending = False
            trace = None
            if process.status != 'ready':
                break
            if (time.perf_counter() - started) * 1000 >= SCHEDULER_TIME_SLICE_MS:
                break
    except Exception as error:
        logger.exception('failed to execute process %s', process_id)
        process.finish('failed', error=str(error), record_event=False)
        child = child_terminal = None
        _finish_call_trace(process, 'failed', str(error))
        if trace_pending and trace is not None:
            trace.update(status='failed', error=str(error))
    finally:
        elapsed_ms = (time.perf_counter() - started) * 1000
        process.active_duration_ms += elapsed_ms
        if trace_pending and trace is not None:
            trace['duration_ms'] = round((time.perf_counter() - node_started) * 1000)
            if trace['status'] != 'waiting':
                trace['finished_at'] = datetime.now(timezone.utc).isoformat()
            process.node_trace.append(trace)
        process.context_ids = sorted(context_ids)
        runtime_maps = [workflow_map, *(frame['workflow'] for frame in process.function_stack)]
        for node in (node for graph in runtime_maps if isinstance(graph, list) for node in graph):
            if isinstance(node, dict):
                node.pop('_workflow_invocation_id', None)
                node.pop('_workflow_ancestor_invocation_ids', None)
                node.pop('_workflow_context_ids', None)
                node.pop('_selected_control_port', None)
                node.pop('_handled_subprocess_error', None)
        current_workflow_process.reset(process_token)
        current_persistent_invocation_id.reset(context_token)
    if isinstance(workflow_map, list):
        process.workflow = json.dumps(workflow_map, ensure_ascii=False, allow_nan=False)
    if process.status in TERMINAL_STATUSES:
        process.finish(
            process.status, finished_at=datetime.now(timezone.utc).isoformat(),
            error=process.error, record_event=False,
        )
    if child is not None:
        committed = spawn_child_and_suspend_parent(
            client, process, child, child_terminal
        )
    else:
        committed = commit_execution_slice(client, process)
    if committed.status in TERMINAL_STATUSES:
        # Include Contexts created by an in-flight node after cancellation.
        _cleanup_process_contexts(process)
    if committed.execution_id == process.execution_id and committed.status == process.status:
        _sync_process_observability(committed)
        _sync_related_process_logs(
            committed.terminal_process_id if committed.status in TERMINAL_STATUSES else None,
            committed.parent_process_id if committed.status in TERMINAL_STATUSES else None,
            child.process_id if child else None,
            child_terminal.process_id if child_terminal else None,
        )
    return committed


def schedule_once(timeout: int = 0) -> Process | None:
    """Run one kernel step; wait on public events only when no process is ready.

    A single runtime owns the ready queue. New runnable work while idle comes
    from external events, so the private queue does not need a blocking wait.
    """
    client = get_connection()
    event_client = get_event_connection()
    process_id = client.rpop(READY_PROCESSES)
    if process_id is not None:
        result = Executor(process_id)
        drain_external_events(client, event_client)
        return result
    item = event_client.brpop(EXTERNAL_EVENTS, timeout=timeout)
    if item is None:
        return None
    handle_external_event(client, item[1])
    drain_external_events(client, event_client)
    return None


def Scheduler(timeout: int = 0) -> None:
    """Block for work, execute ready processes, and drain events between steps."""
    while True:
        schedule_once(timeout=timeout)


def rebuild_process_observability(client) -> None:
    """Repair history left behind by a crash or MongoDB outage from Redis."""
    for raw in client.hgetall(PROCESSTABLE).values():
        _sync_process_observability(Process.from_record(json.loads(raw)))
    from process_recovery import reconcile_lost_processes
    try:
        reconcile_lost_processes(client, _get_process_log_collection())
    except PyMongoError:
        logger.exception('failed to reconcile lost process history; retry at next startup')


def main() -> None:
    from tools import workspace as _workspace_tools  # noqa: F401

    client = get_connection()
    rebuild_public_scheduler(client, PROCESSTABLE, READY_PROCESSES)
    rebuild_process_observability(client)
    logger.info('Process scheduler started')
    Scheduler()


if __name__ == '__main__':
    main()
