"""Exercise real scheduler and API paths with transaction-aware in-memory Redis."""
import copy
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from redis.exceptions import WatchError

import main
import r
from process_creation import build_workflow_process
from workflow_nodes import WorkflowStep, workflow_wait_terminal_event, run_workflow_map
from terminal_repository import terminal_process_context

sys.path.append(str(Path(__file__).resolve().parent.parent / "webui_py"))
from terminal import TerminalRequest, create_terminal_router


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


PORTS = [{"name": "text", "type": "content"}]


def edge(source, target, out="control-out", into="control-in", kind="control"):
    return {"fromId": source, "toId": target, "fromPortId": out, "toPortId": into, "type": kind}


def document(name, child=None, wait=False, output_terminal=False):
    nodes = [{"id": "in", "type": "input", "workflowPorts": [{"id": "workflow:text", **PORTS[0]}]}]
    connections = []
    previous = "in"
    data_source = "in"
    if child:
        nodes.append({"id": "call", "type": "workflow", "arguments": {"workflow_name": child},
                      "input_ports": PORTS, "output_ports": PORTS})
        connections += [edge(previous, "call"), edge("in", "call", "workflow:text", "workflow:text", "content")]
        previous = data_source = "call"
    if wait:
        nodes.append({"id": "wait", "type": "wait_terminal_event"})
        connections.append(edge(previous, "wait"))
        previous = "wait"
    if output_terminal:
        nodes.append({"id": "term", "type": "output_to_terminal"})
        connections += [edge(previous, "term"), edge(data_source, "term", "workflow:text", "content-in", "content")]
        previous = "term"
    nodes.append({"id": "out", "type": "output", "workflowPorts": [{"id": "workflow:text", **PORTS[0]}]})
    connections += [edge(previous, "out"), edge(data_source, "out", "workflow:text", "workflow:text", "content")]
    return {"schema_version": "2.0", "name": name, "input_ports": PORTS, "output_ports": PORTS,
            "nodes": nodes, "connections": connections, "metadata": {"structs": []},
            "workflow_nodes": [{"name": child, "input_ports": PORTS, "output_ports": PORTS}] if child else []}


class ProcessWorkflowTest(unittest.TestCase):
    def setUp(self):
        self.redis = MemoryRedis()
        self.documents = {}
        self.logs = MagicMock()
        self.runs = MagicMock()
        self.output = MagicMock()
        for target, value in [
            ("main.get_connection", self.redis),
            ("workflow_context_repository.get_connection", self.redis),
            ("main._get_process_log_collection", self.logs),
            ("workflow_run_repository.get_workflow_log_collection", self.runs),
        ]:
            patcher = patch(target, return_value=value)
            patcher.start()
            self.addCleanup(patcher.stop)
        for target, kwargs in [
            ("workflow_parser._read_workspace_workflow_by_name", {"side_effect": lambda name: copy.deepcopy(self.documents[name])}),
            ("terminal_repository.append_terminal_output", {"side_effect": self.output}),
        ]:
            patcher = patch(target, **kwargs)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.messages = MagicMock()
        router = create_terminal_router(self.redis, self.messages)
        self.submit = next(route.endpoint for route in router.routes if route.path == "/api/terminal")

    def start(self, workflow, text="hello", inputs=None):
        process = build_workflow_process(workflow, inputs if inputs is not None else {"text": text}, "root-file")
        return main.create_process(process)

    def drain(self):
        results = []
        for _ in range(100):
            result = main.schedule_once(timeout=1)
            if result is None:
                return results
            results.append(result)
        self.fail("scheduler failed to quiesce")

    def workflows(self):
        return [json.loads(raw) for raw in self.redis.hgetall(r.PROCESSTABLE).values()
                if json.loads(raw).get("process_type") == "workflow"]

    def send(self, process, text="continue"):
        return self.submit(TerminalRequest(content=text, terminal_process_id=process["terminal_process_id"]))

    def test_nested_child_waits_and_returns_without_recreating_calls(self):
        self.documents = {"Middle.flow": document("Middle", "Leaf.flow"),
                          "Leaf.flow": document("Leaf", wait=True, output_terminal=True)}
        root = self.start(document("Root", "Middle.flow"))
        self.drain()
        processes = {item["workflow_name"]: item for item in self.workflows()}
        self.assertEqual(len(processes), 3)
        self.assertTrue(all(item["status"] == "blocked" for item in processes.values()))
        leaf = processes["Leaf"]
        self.assertEqual(leaf["root_process_id"], root["process_id"])
        self.assertEqual(leaf["ancestor_invocation_ids"], [root["process_id"], processes["Middle"]["process_id"]])
        self.assertEqual(len({item["terminal_process_id"] for item in processes.values()}), 3)
        # Parent terminal messages cannot satisfy a wait on child exit.
        self.send(root)
        self.assertEqual(main.read_process(root["process_id"])["status"], "blocked")
        self.assertFalse(self.redis.lists[r.READY_PROCESSES])
        self.send(leaf)
        self.send(leaf)
        self.assertEqual(self.redis.lists[r.READY_PROCESSES], [leaf["process_id"]])
        self.drain()
        for process in self.workflows():
            self.assertEqual(process["status"], "completed")
            self.assertEqual(process["result"], {"text": "hello"})
            self.assertIsNone(process["pending_call"])
            self.assertEqual(main.read_process(process["terminal_process_id"])["status"], "terminated")
            self.assertTrue(all(entry["status"] == "completed" for entry in process["node_trace"]))
        self.assertEqual(len(self.workflows()), 3)
        self.output.assert_called_once_with("hello", terminal_process_id=leaf["terminal_process_id"])
        self.assertFalse(self.redis.sets[r.BLOCKED_PROCESSES])

    def test_child_failure_propagates_through_all_ancestors(self):
        self.documents = {"Middle.flow": document("Middle", "Leaf.flow"),
                          "Leaf.flow": document("Leaf", wait=True, output_terminal=True)}
        root = self.start(document("Root", "Middle.flow"), text=" ")
        self.drain()
        leaf = next(item for item in self.workflows() if item["workflow_name"] == "Leaf")
        self.send(leaf)
        with self.assertLogs("main", level="ERROR"):
            self.drain()
        for process in self.workflows():
            self.assertEqual(process["status"], "failed")
            self.assertIn("non-empty text", process["error"])
        self.assertIn(leaf["process_id"], main.read_process(root["process_id"])["error"])
        self.assertFalse(self.redis.sets[r.BLOCKED_PROCESSES])

    def test_cancel_root_cancels_descendants_and_fences_late_commits(self):
        self.documents = {"Child.flow": document("Child", wait=True)}
        root = self.start(document("Root", "Child.flow"))
        self.drain()
        child = next(item for item in self.workflows() if item["workflow_name"] == "Child")
        self.send(child)
        claimed, ok = r.claim_process(self.redis, child["process_id"])
        self.assertTrue(ok)
        main.terminate_process(root["process_id"])
        claimed["status"] = "ready"
        saved = r.commit_process(self.redis, claimed)
        self.assertEqual(saved["status"], "terminated")
        self.assertTrue(all(item["status"] == "terminated" for item in self.workflows()))
        self.assertFalse(self.redis.lists[r.READY_PROCESSES])
        self.assertFalse(self.redis.sets[r.BLOCKED_PROCESSES])

    def test_cancel_child_wakes_parent_and_propagates_failure(self):
        self.documents = {"Child.flow": document("Child", wait=True)}
        root = self.start(document("Root", "Child.flow"))
        self.drain()
        child = next(item for item in self.workflows() if item["workflow_name"] == "Child")
        main.terminate_process(child["process_id"])
        self.assertEqual(main.read_process(root["process_id"])["status"], "ready")
        with self.assertLogs("main", level="ERROR"):
            self.drain()
        self.assertEqual(main.read_process(root["process_id"])["status"], "failed")

    def test_wait_does_not_count_wall_time_toward_execution_timeout(self):
        root = self.start(document("Root", wait=True))
        self.drain()
        saved = main.read_process(root["process_id"])
        saved["start_time"] = "2020-01-01T00:00:00+00:00"
        main.write_process(saved)
        self.send(saved)
        self.drain()
        self.assertEqual(main.read_process(saved["process_id"])["status"], "completed")

    def test_stale_queue_entries_never_execute_blocked_or_completed_nodes(self):
        root = self.start(document("Root", wait=True))
        self.drain()
        process_id = root["process_id"]
        before = main.read_process(process_id)
        self.redis.lpush(r.READY_PROCESSES, process_id)
        self.drain()
        self.assertEqual(main.read_process(process_id), before)
        self.send(root)
        self.drain()
        before = main.read_process(process_id)
        self.redis.lpush(r.READY_PROCESSES, process_id)
        self.drain()
        self.assertEqual(main.read_process(process_id), before)

    def test_wakeup_retry_preserves_concurrent_process_update(self):
        root = self.start(document("Root", wait=True))
        self.drain()
        def concurrent_update():
            saved = main.read_process(root["process_id"])
            saved["test_marker"] = "preserved"
            main.write_process(saved)
        self.redis.before_execute = concurrent_update
        self.send(root)
        self.assertEqual(main.read_process(root["process_id"])["test_marker"], "preserved")
        self.assertEqual(self.redis.lists[r.READY_PROCESSES], [root["process_id"]])

    def test_context_scope_survives_nested_process_scheduling_and_cleanup(self):
        previous_docs = dict(self.documents)
        self.addCleanup(lambda: self.documents.clear() or self.documents.update(previous_docs))
        from test_workflow_child_context import root, wrapper, leaf
        leaf_doc = leaf()
        # Suspend after the child has created its own Context.
        leaf_doc["nodes"].insert(-1, {"id": "wait", "type": "wait_terminal_event"})
        for connection in leaf_doc["connections"]:
            if connection["fromId"] == "local" and connection["type"] == "control":
                connection["toId"] = "wait"
        leaf_doc["connections"].append(edge("wait", "final"))
        self.documents = {"Middle": wrapper("Middle", "Leaf"), "Leaf": leaf_doc}
        process = self.start(root("Middle"), inputs={"context_id": "unused", "items": ["parent"]})
        self.drain()
        self.assertIn("workflow-context:root-list", self.redis.hashes)
        self.assertIn("workflow-context:child-local", self.redis.hashes)
        self.assertNotIn("workflow-context:root-list", self.redis.expirations)
        self.assertNotIn("workflow-context:child-local", self.redis.expirations)
        child = next(item for item in self.workflows() if item["workflow_name"] == "Leaf")
        self.send(child)
        self.drain()
        self.assertEqual(main.read_process(process["process_id"])["result"], {"items": ["parent", "child"]})
        self.assertFalse(any(key.startswith("workflow-context:") for key in self.redis.hashes))

    def test_timeout_on_active_execution_fails_process_and_cleans_contexts(self):
        root = self.start(document("Root"))
        root["active_duration_ms"] = 180001
        main.write_process(root)
        with self.assertLogs("main", level="ERROR"):
            self.drain()
        self.assertEqual(main.read_process(root["process_id"])["status"], "failed")
        self.assertFalse(self.redis.lists[r.READY_PROCESSES])

    def test_wait_node_requires_scheduler_and_process_terminal(self):
        node = {"id": "wait", "type": "wait_terminal_event", "successors": {"next": 1}}
        with self.assertRaisesRegex(ValueError, "process terminal"):
            workflow_wait_terminal_event(0, [node])
        with terminal_process_context("terminal"):
            outcome = workflow_wait_terminal_event(0, [node])
            self.assertIsInstance(outcome, WorkflowStep)
            with self.assertRaisesRegex(ValueError, "process scheduler"):
                run_workflow_map([node], 0)


if __name__ == "__main__":
    unittest.main()
