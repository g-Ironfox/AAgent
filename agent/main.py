import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any
from process_creation import initialize_process_pair

from pymongo import ASCENDING, MongoClient

from r import BLOCKED_PROCESSES, PROCESSTABLE, READY_PROCESSES, get_connection
from workflow_nodes import WORKFLOW_END, execute_node
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


def _record_node_timing(
    process: dict,
    node: dict,
    started_at: datetime,
    finished_at: datetime,
    duration_ms: int,
    status: str,
) -> None:
    _get_process_log_collection().update_one(
        {'process_id': process['process_id']},
        {
            '$setOnInsert': {
                'process_id': process['process_id'],
                'start_time': _parse_start_time(process['start_time']),
                'status': 'running',
            },
            '$push': {
                'nodes': {
                    'node_id': node.get('id'),
                    'node_name': node.get('name'),
                    'node_type': node.get('type'),
                    'started_at': started_at,
                    'finished_at': finished_at,
                    'duration_ms': duration_ms,
                    'status': status,
                }
            }
        },
        upsert=True,
    )


def _record_process_completion(
    process: dict,
    finished_at: datetime,
    duration_ms: int,
    status: str = 'completed',
) -> None:
    _get_process_log_collection().update_one(
        {'process_id': process['process_id']},
        {
            '$setOnInsert': {
                'process_id': process['process_id'],
                'start_time': _parse_start_time(process['start_time']),
                'nodes': [],
            },
            '$set': {
                'finished_at': finished_at,
                'total_duration_ms': duration_ms,
                'status': status,
            }
        },
        upsert=True,
    )


def _initialize_process_timing(process: dict) -> None:
    try:
        _get_process_log_collection().update_one(
            {'process_id': process['process_id']},
            {
                '$setOnInsert': {
                    'process_id': process['process_id'],
                    'start_time': _parse_start_time(process['start_time']),
                    'nodes': [],
                    'status': 'running',
                }
            },
            upsert=True,
        )
    except Exception:
        logger.exception(
            'failed to initialize process timing for %s', process['process_id']
        )


def _enqueue_ready_process(process_id: str) -> None:
    client = get_connection()
    client.srem(BLOCKED_PROCESSES, process_id)
    client.lpush(READY_PROCESSES, process_id)


def read_process(process_id: str) -> dict:
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
    if not isinstance(process, dict) or process.get('process_id') != process_id:
        raise ValueError(f'invalid process data: {process_id}')
    return process


def write_process(process: dict) -> bool:
    """Replace a complete process JSON record, keyed by process_id."""
    if not isinstance(process, dict):
        raise ValueError('process must be a dictionary')
    process_id = process.get('process_id')
    if not isinstance(process_id, str) or not process_id:
        raise ValueError('process_id must be a non-empty string')
    try:
        raw = json.dumps(process, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as error:
        raise ValueError(f'process data is not JSON serializable: {process_id}') from error
    get_connection().hset(PROCESSTABLE, process_id, raw)
    return True


def create_process(process: dict) -> dict:
    """Create a runnable process and its passive, process-scoped terminal."""
    terminal_process = initialize_process_pair(process)

    write_process(process)
    write_process(terminal_process)
    _initialize_process_timing(process)
    _enqueue_ready_process(process['process_id'])
    return process


def block_process(process_id: str, wait_for: dict) -> dict:
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
    process['status'] = 'blocked'
    process['wait_for'] = dict(wait_for)
    write_process(process)
    client = get_connection()
    client.lrem(READY_PROCESSES, 0, process_id)
    client.sadd(BLOCKED_PROCESSES, process_id)
    return process


def wake_process(process_id: str, source_process_id: str, event_kind: str) -> dict:
    """Wake a process only when the source process and event kind both match."""
    if not isinstance(source_process_id, str) or not source_process_id:
        raise ValueError('source_process_id must be a non-empty string')
    if event_kind not in {'process_exit', 'terminal_message'}:
        raise ValueError('unsupported process wake event kind')
    process = read_process(process_id)
    if (
        process.get('status') != 'blocked'
        or process.get('wait_for')
        != {'kind': event_kind, 'process_id': source_process_id}
    ):
        return process
    process['status'] = 'ready'
    process['wait_for'] = None
    write_process(process)
    _enqueue_ready_process(process_id)
    return process


def _terminate_terminal_process(parent_process: dict) -> None:
    terminal_process_id = parent_process.get('terminal_process_id')
    if not isinstance(terminal_process_id, str) or not terminal_process_id:
        return
    try:
        terminal_process = read_process(terminal_process_id)
    except KeyError:
        logger.warning(
            'terminal process %s missing for parent %s',
            terminal_process_id,
            parent_process.get('process_id'),
        )
        return
    if (
        terminal_process.get('process_type') != 'terminal'
        or terminal_process.get('parent_process_id')
        != parent_process.get('process_id')
    ):
        logger.error(
            'terminal process %s has an invalid parent link', terminal_process_id
        )
        return
    if terminal_process.get('status') == 'terminated':
        return

    terminal_process['status'] = 'terminated'
    terminal_process['wait_for'] = None
    terminal_process['finished_at'] = datetime.now(timezone.utc).isoformat()
    write_process(terminal_process)
    client = get_connection()
    client.lrem(READY_PROCESSES, 0, terminal_process_id)
    client.srem(BLOCKED_PROCESSES, terminal_process_id)


def Executor(process_id: str) -> dict:
    process = read_process(process_id)

    workflow_json = process.get('workflow')
    if not isinstance(workflow_json, str):
        raise ValueError(f'invalid workflow data: {process_id}')
    try:
        workflow_map = json.loads(workflow_json)
    except (TypeError, ValueError) as error:
        raise ValueError(f'invalid workflow data: {process_id}') from error
    if not isinstance(workflow_map, list) or not all(
        isinstance(node, dict) for node in workflow_map
    ):
        raise ValueError(f'invalid workflow data: {process_id}')

    current_node_id = process.get('current_node_id')
    if isinstance(current_node_id, bool) or not isinstance(current_node_id, int):
        raise ValueError(f'invalid current_node_id: {process_id}')

    if not process.get('start_time'):
        raise ValueError(f'process start_time is missing: {process_id}')
    process_start_time = _parse_start_time(process['start_time'])

    node = (
        workflow_map[current_node_id]
        if 0 <= current_node_id < len(workflow_map)
        else {}
    )
    node_started_at = datetime.now(timezone.utc)
    node_started_monotonic = time.perf_counter()
    try:
        with terminal_process_context(process.get('terminal_process_id')):
            next_node_id = execute_node(current_node_id, workflow_map)
    except Exception:
        node_finished_at = datetime.now(timezone.utc)
        try:
            _record_node_timing(
                process,
                node,
                node_started_at,
                node_finished_at,
                round((time.perf_counter() - node_started_monotonic) * 1000),
                'failed',
            )
        except Exception:
            logger.exception('failed to record node timing for process %s', process_id)
        raise
    node_finished_at = datetime.now(timezone.utc)
    try:
        _record_node_timing(
            process,
            node,
            node_started_at,
            node_finished_at,
            round((time.perf_counter() - node_started_monotonic) * 1000),
            'completed',
        )
    except Exception:
        logger.exception('failed to record node timing for process %s', process_id)
    process['workflow'] = json.dumps(
        workflow_map, ensure_ascii=False, allow_nan=False
    )
    process['current_node_id'] = next_node_id
    if next_node_id == WORKFLOW_END:
        process['status'] = 'completed'
        try:
            _record_process_completion(
                process,
                node_finished_at,
                round(
                    (node_finished_at - process_start_time).total_seconds() * 1000
                ),
            )
        except Exception:
            logger.exception('failed to record completion for process %s', process_id)
    write_process(process)
    if process.get('status') == 'completed':
        try:
            _terminate_terminal_process(process)
        except Exception:
            logger.exception(
                'failed to terminate terminal process for %s', process_id
            )
    return process


def schedule_once(timeout: int = 5) -> dict | None:
    """Block for a runnable process, execute one node, then reschedule its state."""
    item = get_connection().brpop(READY_PROCESSES, timeout=timeout)
    if item is None:
        return None
    _, process_id = item
    try:
        process = Executor(process_id)
    except Exception as error:
        logger.exception('failed to execute process %s', process_id)
        process = read_process(process_id)
        process['status'] = 'failed'
        process['error'] = str(error)
        write_process(process)
        try:
            _terminate_terminal_process(process)
        except Exception:
            logger.exception(
                'failed to terminate terminal process for failed process %s',
                process_id,
            )
        try:
            finished_at = datetime.now(timezone.utc)
            start_time = _parse_start_time(process['start_time'])
            _record_process_completion(
                process,
                finished_at,
                round((finished_at - start_time).total_seconds() * 1000),
                status='failed',
            )
        except Exception:
            logger.exception('failed to record failed process %s', process_id)
        return process

    client = get_connection()
    status = process.get('status')
    if status == 'blocked':
        client.sadd(BLOCKED_PROCESSES, process_id)
    elif status == 'completed':
        client.srem(BLOCKED_PROCESSES, process_id)
    else:
        process['status'] = 'ready'
        write_process(process)
        _enqueue_ready_process(process_id)
    return process


def Scheduler(timeout: int = 5) -> None:
    """Run the blocking scheduler loop; BRPOP sleeps while no process is ready."""
    while True:
        schedule_once(timeout=timeout)


def main() -> None:
    from tools import workspace as _workspace_tools  # noqa: F401

    logger.info('Process scheduler started')
    Scheduler()


if __name__ == '__main__':
    main()
