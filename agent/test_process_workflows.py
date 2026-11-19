"""Exercise real scheduler and API paths with transaction-aware in-memory Redis."""
import copy
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from test_support import MemoryRedis

import main
import process_repository as r
from process_creation import build_workflow_process
from workflow_nodes import WorkflowStep, workflow_wait_terminal_event
from terminal_repository import terminal_process_context

sys.path.append(str(Path(__file__).resolve().parent.parent / "webui_py"))
from terminal import TerminalRequest, create_terminal_router
from processes import CreateProcessRequest, create_processes_router


PORTS = [{"name": "text", "type": "content"}]


def edge(source, target, out="control-out", into="control-in", kind="control"):
    return {"fromId": source, "toId": target, "fromPortId": out, "toPortId": into, "type": kind}


def document(name, child=None, wait=False, output_terminal=False):
    nodes = [{"id": "in", "type": "input", "workflowPorts": [{"id": "workflow:text", **PORTS[0]}]}]
    connections = []
    previous = "in"
    data_source = "in"
    if child:
        nodes.append({"id": "call", "type": "spawn_and_wait_subprocess", "arguments": {"workflow_file": child},
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
    return {"schema_version": "2.0", "input_ports": PORTS, "output_ports": PORTS,
            "nodes": nodes, "connections": connections, "metadata": {"structs": []},
            "subprocess_workflow_files": [{"name": child, "input_ports": PORTS, "output_ports": PORTS}] if child else []}


class ProcessWorkflowTest(unittest.TestCase):
    def setUp(self):
        self.redis = MemoryRedis()
        self.public_redis = self.redis.with_db(r.REDIS_PUBLIC_DB)
        self.documents = {}
        self.logs = MagicMock()
        self.runs = MagicMock()
        self.output = MagicMock()
        for target, value in [
            ("main.get_connection", self.redis),
            ("main.get_event_connection", self.public_redis),
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
        router = create_terminal_router(self.public_redis, self.messages)
        self.submit = next(route.endpoint for route in router.routes if route.path == "/api/terminal")
        self.sessions = next(route.endpoint for route in router.routes if route.path == "/api/terminal/sessions")

    def start(self, workflow, text="hello", inputs=None):
        process = build_workflow_process(
            workflow,
            inputs if inputs is not None else {"text": text},
            "root-file",
            "Root.flow",
            "terminal-root",
        )
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
        result = self.submit(TerminalRequest(content=text, terminal_id=process["terminal_id"]))
        main.drain_external_events(self.redis, self.public_redis)
        return result

    def terminal_session(self, root):
        return json.loads(self.public_redis.hget(r.TERMINAL_SESSIONS, root["terminal_id"]))

    def assert_database_isolation(self):
        internal_keys = {r.PROCESSTABLE, r.READY_PROCESSES, r.BLOCKED_PROCESSES, r.TERMINAL_INDEX}
        public_keys = {r.EXTERNAL_EVENTS, r.TERMINAL_SESSIONS}
        for state in ("hashes", "lists", "sets"):
            self.assertTrue(internal_keys.isdisjoint(getattr(self.public_redis, state)))
            self.assertTrue(public_keys.isdisjoint(getattr(self.redis, state)))
        self.assertFalse(any(key.startswith("workflow-context:") for key in self.public_redis.hashes))

    def test_webui_creation_and_terminal_input_cross_only_the_public_database(self):
        store = MagicMock()
        store.get_file.return_value = {
            "file_id": "root-file", "name": "Root.flow",
            "content": json.dumps(document("Root", wait=True)),
        }
        router = create_processes_router(self.public_redis, store)
        create = next(route.endpoint for route in router.routes if route.path == "/api/processes")
        response = create(CreateProcessRequest(
            workflow_file_id="root-file", terminal_id="terminal-root", inputs={"text": "hello"},
        ))
        self.assertEqual(response, {
            "status": "queued", "terminal_id": "terminal-root", "workflow_name": "Root.flow",
        })
        self.assertEqual(self.redis.hgetall(r.PROCESSTABLE), {})
        self.assertEqual(len(self.public_redis.lists[r.EXTERNAL_EVENTS]), 1)

        # Idle runtime wakes on the public event, then executes private ready work.
        self.assertIsNone(main.schedule_once(timeout=1))
        root, = self.workflows()
        self.assertNotEqual(root["process_id"], "terminal-root")
        self.assertEqual(self.redis.lists[r.READY_PROCESSES], [root["process_id"]])
        self.assertEqual(self.terminal_session(root)["status"], "open")
        self.assert_database_isolation()
        self.drain()
        self.assertEqual(main.read_process(root["process_id"])["status"], "blocked")

        self.submit(TerminalRequest(content="continue", terminal_id="terminal-root"))
        self.assertEqual(main.read_process(root["process_id"])["status"], "blocked")
        self.assertIsNone(main.schedule_once(timeout=1))
        self.assertEqual(main.read_process(root["process_id"])["status"], "ready")
        self.drain()
        self.assertEqual(main.read_process(root["process_id"])["status"], "completed")
        self.assertEqual(self.terminal_session(root)["status"], "closed")
        self.assert_database_isolation()

    def test_public_terminal_stays_open_after_child_exit_and_closes_with_root(self):
        self.documents = {"Child.flow": document("Child", wait=True)}
        root = self.start(document("Root", "Child.flow", wait=True))
        session = self.terminal_session(root)
        self.assertEqual(session["status"], "open")
        self.assertIsNone(session["closed_at"])
        self.assertFalse({"process_id", "root_process_id", "terminal_process_id"} & session.keys())
        self.drain()
        child = next(item for item in self.workflows() if item["workflow_name"] == "Child.flow")
        self.assertEqual(self.terminal_session(root)["workflow_name"], "Child.flow")
        self.send(child)
        self.drain()
        self.assertEqual(main.read_process(child["process_id"])["status"], "completed")
        self.assertEqual(main.read_process(child["terminal_process_id"])["status"], "terminated")
        session = self.terminal_session(root)
        self.assertEqual(session["status"], "open")
        self.assertEqual(session["workflow_name"], "Root.flow")
        self.assertEqual(self.sessions()["sessions"], [session])
        self.assertEqual(session["wait_kind"], "terminal_message")
        self.assertEqual(session["start_time"], root["start_time"])
        self.assertEqual(self.redis.hget(r.TERMINAL_INDEX, root["terminal_id"]), root["terminal_process_id"])
        self.send(root)
        self.assertEqual(self.terminal_session(root)["workflow_status"], "ready")
        self.drain()
        session = self.terminal_session(root)
        self.assertEqual(session["status"], "closed")
        self.assertEqual(session["closed_at"], main.read_process(root["process_id"])["finished_at"])
        self.assertIsNone(self.redis.hget(r.TERMINAL_INDEX, root["terminal_id"]))

    def test_child_cancellation_keeps_public_terminal_open_until_root_fails(self):
        self.documents = {"Child.flow": document("Child", wait=True)}
        root = self.start(document("Root", "Child.flow"))
        self.drain()
        child = next(item for item in self.workflows() if item["workflow_name"] == "Child.flow")
        main.terminate_process(child["process_id"])
        self.assertEqual(self.terminal_session(root)["status"], "open")
        self.assertIsNone(self.terminal_session(root)["closed_at"])
        with self.assertLogs("main", level="ERROR"):
            self.drain()
        self.assertEqual(self.terminal_session(root)["status"], "closed")
        self.assertEqual(self.terminal_session(root)["workflow_status"], "failed")

    def test_root_cancellation_closes_public_terminal_and_fences_late_commit(self):
        root = self.start(document("Root", wait=True))
        claimed, ok = r.claim_process(self.redis, root["process_id"])
        self.assertTrue(ok)
        main.terminate_process(root["process_id"])
        closed = self.terminal_session(root)
        self.assertEqual(closed["status"], "closed")
        self.assertEqual(closed["workflow_status"], "terminated")
        self.assertEqual(self.sessions()["sessions"], [closed])
        self.assertIsNotNone(closed["closed_at"])
        self.assertIsNone(self.redis.hget(r.TERMINAL_INDEX, root["terminal_id"]))
        claimed["status"] = "ready"
        r.commit_process(self.redis, claimed)
        self.assertEqual(self.terminal_session(root), closed)

    def test_root_identity_and_self_recursion_use_the_external_filename(self):
        graph = document("ignored display name", "Root.flow")
        graph["name"] = "outdated display name"
        self.documents = {"Root.flow": graph}
        root = self.start(graph)
        self.assertEqual(root["workflow_name"], "Root.flow")
        self.assertEqual(root["workflow_file"], "Root.flow")
        self.assertEqual(root["call_stack"], ["Root.flow"])
        with self.assertLogs(main.logger, level="ERROR"):
            self.drain()
        process = main.read_process(root["process_id"])
        self.assertEqual(process["status"], "failed")
        self.assertIn("Root.flow -> Root.flow", process["error"])
        self.assertEqual(len(self.workflows()), 1)

    def test_nested_child_waits_and_returns_without_recreating_calls(self):
        self.documents = {"Middle.flow": document("Middle", "Leaf.flow"),
                          "Leaf.flow": document("Leaf", wait=True, output_terminal=True)}
        root = self.start(document("Root", "Middle.flow"))
        self.drain()
        processes = {item["workflow_name"]: item for item in self.workflows()}
        self.assertEqual(len(processes), 3)
        self.assertTrue(all(item["status"] == "blocked" for item in processes.values()))
        leaf = processes["Leaf.flow"]
        self.assertEqual(leaf["current_node_id"], 1)
        self.assertEqual(leaf["control_port"], "next")
        self.assertNotIn("next_node_id", leaf)
        self.assertEqual(leaf["root_process_id"], root["process_id"])
        self.assertEqual(leaf["ancestor_invocation_ids"], [root["process_id"], processes["Middle.flow"]["process_id"]])
        self.assertEqual(len({item["terminal_process_id"] for item in processes.values()}), 3)
        # The public terminal ID routes to the currently active descendant wait.
        self.send(root)
        self.assertEqual(main.read_process(root["process_id"])["status"], "blocked")
        self.assertEqual(self.redis.lists[r.READY_PROCESSES], [leaf["process_id"]])
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
        self.output.assert_called_once_with(
            "hello",
            terminal_id=leaf["terminal_id"],
            terminal_process_id=leaf["terminal_process_id"],
        )
        self.assertFalse(self.redis.sets[r.BLOCKED_PROCESSES])

    def latest_log(self, process_id):
        return next(call.args[1]["$set"] for call in reversed(self.logs.update_one.call_args_list)
                    if call.args[0] == {"process_id": process_id} and "$set" in call.args[1])

    def test_process_logs_capture_creation_suspend_wake_and_completion(self):
        root = self.start(document("Root", wait=True))
        process_id = root["process_id"]
        self.assertEqual(self.latest_log(process_id)["status"], "ready")
        self.assertEqual(self.latest_log(root["terminal_process_id"])["process_type"], "terminal")
        self.drain()
        blocked = self.latest_log(process_id)
        self.assertEqual(blocked["status"], "blocked")
        self.assertEqual(blocked["events"][-1]["event"], "blocked")
        self.assertEqual(blocked["events"][-1]["wait_for"], blocked["wait_for"])
        self.assertEqual(blocked["wait_for"]["kind"], "terminal_message")
        self.send(root)
        ready = self.latest_log(process_id)
        self.assertEqual(ready["status"], "ready")
        self.assertIsNone(ready["wait_for"])
        self.assertEqual(ready["events"][-1]["event"], "woken")
        self.assertEqual(ready["events"][-1]["wait_for"], blocked["wait_for"])
        self.send(root)
        self.assertEqual(self.latest_log(process_id)["events"], ready["events"])
        self.drain()
        completed = self.latest_log(process_id)
        self.assertEqual(completed["status"], "completed")
        self.assertEqual(completed["output"], {"text": "hello"})
        self.assertEqual([event["event"] for event in completed["events"]],
                         ["created", "started", "yielded", "resumed", "blocked", "woken", "resumed", "completed"])
        self.assertTrue(all(event["timestamp"] for event in completed["events"]))
        self.assertEqual(self.latest_log(root["terminal_process_id"])["status"], "terminated")
        self.assertEqual(self.latest_log(root["terminal_process_id"])["events"][-1]["event"], "terminated")

    def test_scheduling_events_capture_each_dispatch_and_return_to_ready(self):
        root = self.start(document("Root"))
        main.schedule_once(timeout=1)
        ready = self.latest_log(root["process_id"])
        self.assertEqual(ready["status"], "ready")
        self.assertEqual([event["event"] for event in ready["events"]],
                         ["created", "started", "yielded"])
        self.assertTrue(ready["events"][1]["dispatch"])
        self.assertIsNotNone(ready["observed_at"].tzinfo)
        main.schedule_once(timeout=1)
        completed = self.latest_log(root["process_id"])
        self.assertEqual([event["event"] for event in completed["events"]],
                         ["created", "started", "yielded", "resumed", "completed"])
        self.assertTrue(completed["events"][-2]["dispatch"])

    def test_child_exit_publishes_parent_wakeup_before_next_execution(self):
        self.documents = {"Child.flow": document("Child", wait=True)}
        root = self.start(document("Root", "Child.flow"))
        self.drain()
        child = next(item for item in self.workflows() if item["workflow_name"] == "Child.flow")
        self.assertEqual(self.latest_log(child["process_id"])["parent_process_id"], root["process_id"])
        self.assertEqual(self.latest_log(root["process_id"])["wait_for"],
                         {"kind": "process_exit", "process_id": child["process_id"]})
        self.send(child)
        while main.read_process(child["process_id"])["status"] != "completed":
            main.schedule_once(timeout=1)
        parent_log = self.latest_log(root["process_id"])
        self.assertEqual(parent_log["status"], "ready")
        self.assertEqual(parent_log["events"][-1]["event"], "woken")
        self.assertEqual(parent_log["events"][-1]["wait_for"]["process_id"], child["process_id"])

    def test_log_database_failure_does_not_interrupt_process_or_lose_events(self):
        self.logs.update_one.side_effect = RuntimeError("logs offline")
        with self.assertLogs("main", level="ERROR"):
            root = self.start(document("Root", wait=True))
            self.drain()
            self.send(root)
            self.drain()
        saved = main.read_process(root["process_id"])
        self.assertEqual(saved["status"], "completed")
        self.assertEqual([item["event"] for item in saved["events"]],
                         ["created", "started", "yielded", "resumed", "blocked", "woken", "resumed", "completed"])

    def test_commit_retry_does_not_duplicate_suspend_events(self):
        root = self.start(document("Root", wait=True))
        main.schedule_once(timeout=1)  # input
        claimed, ok = r.claim_process(self.redis, root["process_id"])
        self.assertTrue(ok)
        claimed.update(status="blocked", wait_for={"kind": "terminal_message", "process_id": root["terminal_process_id"]})
        self.redis.before_execute = lambda: main.write_process(main.read_process(root["process_id"]))
        committed = r.commit_process(self.redis, claimed)
        self.assertEqual([item["event"] for item in committed["events"]].count("blocked"), 1)
        self.assertEqual(main.read_process(root["process_id"])["events"], committed["events"])

    def test_legacy_pending_node_resumes_without_spawning_a_second_child(self):
        self.documents = {"Child.flow": document("Child", wait=True)}
        root = self.start(document("Root", "Child.flow"))
        self.drain()
        parent = main.read_process(root["process_id"])
        compiled = json.loads(parent["workflow"])
        pending_node = compiled[parent["pending_call"]["node_index"]]
        pending_node["type"] = "workflow"
        pending_node["arguments"]["workflow_name"] = pending_node["arguments"].pop("workflow_file")
        parent["workflow"] = json.dumps(compiled)
        self.redis.hset(r.PROCESSTABLE, root["process_id"], json.dumps(parent))
        child = next(item for item in self.workflows() if item["workflow_name"] == "Child.flow")
        self.send(child)
        self.drain()
        restored = main.read_process(root["process_id"])
        self.assertEqual(restored["status"], "completed")
        self.assertEqual(restored["result"], {"text": "hello"})
        self.assertEqual(len(self.workflows()), 2)
        migrated_node = next(node for node in json.loads(restored["workflow"]) if node["id"] == "call")
        self.assertEqual(migrated_node["type"], "spawn_and_wait_subprocess")
        self.assertNotIn("workflow_name", migrated_node["arguments"])

    def test_child_failure_propagates_through_all_ancestors(self):
        self.documents = {"Middle.flow": document("Middle", "Leaf.flow"),
                          "Leaf.flow": document("Leaf", wait=True, output_terminal=True)}
        root = self.start(document("Root", "Middle.flow"), text=" ")
        self.drain()
        leaf = next(item for item in self.workflows() if item["workflow_name"] == "Leaf.flow")
        self.assertEqual(leaf["current_node_id"], 1)
        self.assertEqual(leaf["control_port"], "next")
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
        child = next(item for item in self.workflows() if item["workflow_name"] == "Child.flow")
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
        child = next(item for item in self.workflows() if item["workflow_name"] == "Child.flow")
        main.terminate_process(child["process_id"])
        self.assertEqual(main.read_process(root["process_id"])["status"], "ready")
        self.assertEqual(self.latest_log(root["process_id"])["events"][-1]["event"], "woken")
        self.assertEqual(self.latest_log(child["process_id"])["status"], "terminated")
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
        saved = main.read_process(root["process_id"])
        self.assertEqual(saved["test_marker"], "preserved")
        self.assertEqual([item["event"] for item in saved["events"]].count("woken"), 1)
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
        self.assert_database_isolation()
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

    def test_process_cursor_resolves_successors_from_the_selected_control_port(self):
        workflow = [
            {"type": "router", "data_inputs": {"content-in": [None, "content", "yes"]},
             "successors": {"branch-yes": 1, "branch$others": 2}},
            {"type": "output"}, {"type": "output"},
        ]
        self.assertEqual(main._next_process_node(
            {"current_node_id": -1, "control_port": None},
            [{"type": "input"}, *workflow],
        ), 0)
        from workflow_nodes import execute_node
        execute_node(0, workflow)
        process = {"current_node_id": 0, "control_port": workflow[0]["_selected_control_port"]}
        self.assertEqual(process["control_port"], "branch-yes")
        self.assertEqual(main._next_process_node(process, workflow), 1)
        self.assertNotIn("next_node_id", process)

    def test_wait_node_requires_scheduler_and_process_terminal(self):
        node = {"id": "wait", "type": "wait_terminal_event", "successors": {"next": 1}}
        with self.assertRaisesRegex(ValueError, "process terminal"):
            workflow_wait_terminal_event(0, [node])
        with terminal_process_context("internal-terminal", "public-terminal"):
            outcome = workflow_wait_terminal_event(0, [node])
            self.assertIsInstance(outcome, WorkflowStep)
            self.assertEqual(
                outcome.wait_for,
                {"kind": "terminal_message", "process_id": "internal-terminal"},
            )


if __name__ == "__main__":
    unittest.main()
