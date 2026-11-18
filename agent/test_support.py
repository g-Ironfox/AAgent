"""In-memory infrastructure that exercises the production process scheduler."""

import copy
import json
from contextlib import ExitStack
from uuid import uuid4
from unittest.mock import MagicMock, patch

from redis.exceptions import WatchError


class MemoryRedis:
    def __init__(self):
        self.hashes = {}
        self.lists = {}
        self.sets = {}
        self.versions = {}
        self.expirations = {}
        self.before_execute = None

    def _changed(self, key):
        self.versions[key] = self.versions.get(key, 0) + 1

    def hget(self, key, field):
        return self.hashes.get(key, {}).get(field)

    def hgetall(self, key):
        return dict(self.hashes.get(key, {}))

    def hexists(self, key, field):
        return field in self.hashes.get(key, {})

    def hset(self, key, field=None, value=None, mapping=None):
        self.hashes.setdefault(key, {}).update(mapping if mapping is not None else {field: value})
        self._changed(key)
        return 1

    def lpush(self, key, value):
        self.lists.setdefault(key, []).insert(0, value)
        self._changed(key)
        return len(self.lists[key])

    def lrem(self, key, count, value):
        self.lists[key] = [item for item in self.lists.get(key, []) if item != value]
        self._changed(key)
        return 0

    def brpop(self, key, timeout=0):
        if not self.lists.get(key):
            return None
        self._changed(key)
        return key, self.lists[key].pop()

    def sadd(self, key, value):
        self.sets.setdefault(key, set()).add(value)
        self._changed(key)
        return 1

    def srem(self, key, value):
        self.sets.setdefault(key, set()).discard(value)
        self._changed(key)
        return 1

    def expire(self, key, ttl):
        self.expirations[key] = ttl
        self._changed(key)
        return True

    def persist(self, key):
        self.expirations.pop(key, None)
        self._changed(key)
        return True

    def delete(self, *keys):
        for key in keys:
            self.hashes.pop(key, None)
            self.sets.pop(key, None)
            self.expirations.pop(key, None)
            self._changed(key)
        return len(keys)

    def eval(self, script, key_count, key, *args):
        # Context creation is the only Lua operation used by these scenarios.
        if key in self.hashes:
            return 0
        self.hset(key, mapping=dict(zip(args[:-1:2], args[1:-1:2])))
        if int(args[-1]) > 0:
            self.expire(key, int(args[-1]))
        return 1

    def pipeline(self, transaction=True):
        return MemoryPipeline(self)


class MemoryPipeline:
    def __init__(self, client):
        self.client = client
        self.watched = {}
        self.queued = True
        self.commands = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.commands.clear()

    def watch(self, *keys):
        self.watched = {key: self.client.versions.get(key, 0) for key in keys}
        self.queued = False

    def multi(self):
        self.queued = True

    def execute(self):
        hook, self.client.before_execute = self.client.before_execute, None
        if hook:
            hook()
        if any(self.client.versions.get(key, 0) != version for key, version in self.watched.items()):
            raise WatchError("concurrent update")
        return [getattr(self.client, name)(*args, **kwargs) for name, args, kwargs in self.commands]

    def __getattr__(self, name):
        def command(*args, **kwargs):
            if self.queued:
                self.commands.append((name, args, kwargs))
                return self
            return getattr(self.client, name)(*args, **kwargs)
        return command


def run_scheduled_workflow(workflow_map, start=0, *, workflow_name=None, inputs=None, max_steps=1000):
    """Drive real Executor/Redis transitions; never implement node execution here.

    Node-unit fixtures may start at a non-input node. Add an input shim without
    changing their endpoint indexes. Copy committed graph state back for asserts.
    External services and Context storage remain controlled by each caller.
    """
    import main
    from r import PROCESSTABLE, TERMINAL_STATUSES

    graph = copy.deepcopy(workflow_map)
    input_node = graph[start]
    call_stack = input_node.get("_workflow_call_stack", [])
    name = workflow_name or (call_stack[-1] if call_stack else "test.flow")
    if inputs is None:
        inputs = {}
        for port in input_node.get("workflowPorts", []):
            targets = input_node.get("data_outputs", {}).get(port["id"], [])
            if port["name"] not in inputs and targets:
                target, target_port = targets[0]
                inputs[port["name"]] = copy.deepcopy(graph[target]["data_inputs"][target_port][2])
    shim = input_node.get("type") != "input"
    if shim:
        graph.append({"id": "test-input-" + uuid4().hex, "type": "input",
                      "successors": {"next": start}, "data_inputs": {}, "data_outputs": {}})
    process = {
        "process_id": uuid4().hex, "parent_process_id": "user_interface",
        "workflow_name": name, "workflow_file": name, "call_stack": call_stack or [name],
        "workflow": json.dumps(graph, ensure_ascii=False, allow_nan=False),
        "current_node_id": -1, "control_port": None, "input": inputs,
    }
    redis = MemoryRedis()
    errors = []
    execute_node = main.execute_node

    def capture_error(index, current_graph):
        try:
            return execute_node(index, current_graph)
        except Exception as error:
            errors.append(error)
            raise

    with ExitStack() as stack:
        stack.enter_context(patch("main.get_connection", return_value=redis))
        stack.enter_context(patch("main.execute_node", side_effect=capture_error))
        stack.enter_context(patch("main._get_process_log_collection", return_value=MagicMock()))
        stack.enter_context(patch("workflow_run_repository.get_workflow_log_collection", return_value=MagicMock()))
        main.create_process(process)
        for _ in range(max_steps):
            if main.schedule_once(timeout=1) is None:
                break
        else:
            raise AssertionError(f"scheduler did not quiesce after {max_steps} steps")
        saved = json.loads(redis.hget(PROCESSTABLE, process["process_id"]))
    committed_graph = json.loads(saved["workflow"])
    workflow_map[:] = committed_graph[:-1] if shim else committed_graph
    if saved["status"] == "failed":
        if errors:
            raise errors[0]
        if saved["error"].startswith("workflow execution exceeded"):
            raise TimeoutError(saved["error"])
        raise ValueError(saved["error"])
    if saved["status"] not in TERMINAL_STATUSES:
        raise AssertionError(f"workflow did not complete: {saved['status']}, wait_for={saved.get('wait_for')}")
    return saved.get("result", {})
