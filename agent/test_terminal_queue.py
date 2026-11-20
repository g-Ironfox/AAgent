"""Terminal input consumption and scheduler race regressions using real transactions."""
import copy
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import main
import process_repository as repository
import test_process_workflows as support
from workflow_contract import SUPPORTED_NODE_TYPES
from workflow_nodes import nodes_map
from workflow_validator import WorkflowValidationError, validate_workflow


def queue_document(reads=1):
    doc = support.document("Queue")
    doc["output_ports"] = [{"name": f"batch{i}", "type": "list-content"} for i in range(reads)]
    doc["nodes"][-1]["workflowPorts"] = [
        {"id": "workflow:" + port["name"], **port} for port in doc["output_ports"]]
    doc["nodes"][1:1] = [{"id": f"read{i}", "type": "read_terminal_queue"} for i in range(reads)]
    doc["connections"] = []
    previous = "in"
    for i in range(reads):
        doc["connections"] += [support.edge(previous, f"read{i}"),
            support.edge(f"read{i}", "out", "list-out", f"workflow:batch{i}", "list-content")]
        previous = f"read{i}"
    doc["connections"].append(support.edge(previous, "out"))
    return doc


class TerminalQueueTest(unittest.TestCase):
    setUp = support.ProcessWorkflowTest.setUp
    start = support.ProcessWorkflowTest.start
    send = support.ProcessWorkflowTest.send
    drain = support.ProcessWorkflowTest.drain
    workflows = support.ProcessWorkflowTest.workflows

    def queue(self, process):
        return main.read_process(process["terminal_process_id"])["input_queue"]

    def test_old_nodes_removed_from_contract_handler_and_validation(self):
        for kind in ("read_terminal_input", "wait_terminal_event"):
            self.assertNotIn(kind, SUPPORTED_NODE_TYPES)
            self.assertNotIn(kind, nodes_map)
            doc = queue_document()
            doc["nodes"][1]["type"] = kind
            with self.assertRaises(WorkflowValidationError):
                validate_workflow(doc)

    def test_early_messages_are_buffered_and_consumed_without_mongodb_reads(self):
        root = self.start(queue_document())
        self.send(root, "first")
        self.send(root, "second\nline")
        self.assertEqual(self.queue(root), ["first", "second\nline"])
        self.assertEqual(self.redis.lists[repository.READY_PROCESSES], [root["process_id"]])
        with patch("terminal_repository.get_terminal_collection", side_effect=AssertionError("history read")):
            self.drain()
        saved = main.read_process(root["process_id"])
        self.assertEqual(saved["status"], "completed", saved.get("error"))
        self.assertEqual(saved["result"], {"batch0": ["first", "second\nline"]})
        self.assertEqual(self.queue(root), [])
        self.messages.find.assert_not_called()
        self.messages.delete_many.assert_not_called()

    def test_empty_queue_blocks_and_resume_retries_the_read_once(self):
        root = self.start(queue_document())
        self.drain()
        blocked = main.read_process(root["process_id"])
        self.assertEqual(blocked["status"], "blocked")
        self.assertEqual(blocked["current_node_id"], 0)
        self.assertEqual(blocked["wait_for"], {"kind": "terminal_message", "process_id": root["terminal_process_id"]})
        self.send(root, "one")
        self.send(root, "two")
        self.assertEqual(self.redis.lists[repository.READY_PROCESSES], [root["process_id"]])
        self.drain()
        final = main.read_process(root["process_id"])
        self.assertEqual(final["result"], {"batch0": ["one", "two"]})
        self.assertEqual(sum(e["event"] == "woken" for e in final["events"]), 1)

    def test_consumed_messages_do_not_reappear_in_the_next_read(self):
        root = self.start(queue_document(reads=2))
        self.send(root, "old")
        self.drain()
        self.assertEqual(main.read_process(root["process_id"])["status"], "blocked")
        self.assertEqual(self.queue(root), [])
        self.send(root, "new")
        self.drain()
        self.assertEqual(main.read_process(root["process_id"])["result"],
                         {"batch0": ["old"], "batch1": ["new"]})

    def test_input_between_empty_read_and_suspend_does_not_get_stranded(self):
        root = self.start(queue_document())
        main.schedule_once(timeout=1)
        execute = main.execute_node
        def concurrent_input(index, graph):
            outcome = execute(index, graph)
            # Fire after WATCH but before EXEC, also exercising transaction retry.
            self.redis.before_execute = lambda: self.send(root, "racing input")
            return outcome
        with patch("main.execute_node", side_effect=concurrent_input):
            result = main.schedule_once(timeout=1)
        self.assertEqual(result["status"], "ready")
        self.assertIsNone(result["wait_for"])
        self.drain()
        self.assertEqual(main.read_process(root["process_id"])["result"], {"batch0": ["racing input"]})

    def test_input_appended_during_consumption_is_kept_for_next_read(self):
        root = self.start(queue_document(reads=2))
        self.send(root, "first batch")
        main.schedule_once(timeout=1)
        execute = main.execute_node
        def concurrent_input(index, graph):
            outcome = execute(index, graph)
            self.redis.before_execute = lambda: self.send(root, "later batch")
            return outcome
        with patch("main.execute_node", side_effect=concurrent_input):
            result = main.schedule_once(timeout=1)
        self.assertEqual(result["status"], "ready")
        self.assertEqual(self.queue(root), ["later batch"])
        self.assertNotIn("_terminal_input_batch", result)
        self.drain()
        self.assertEqual(main.read_process(root["process_id"])["result"],
                         {"batch0": ["first batch"], "batch1": ["later batch"]})

    def test_enqueue_retry_does_not_duplicate_messages_or_wakeups(self):
        root = self.start(queue_document())
        self.drain()
        self.redis.before_execute = lambda: main.write_process(main.read_process(root["process_id"]))
        self.send(root, "once")
        self.assertEqual(self.queue(root), ["once"])
        self.assertEqual(self.redis.lists[repository.READY_PROCESSES], [root["process_id"]])
        saved = main.read_process(root["process_id"])
        self.assertEqual(sum(e["event"] == "woken" for e in saved["events"]), 1)

    def test_failed_commit_does_not_consume_input(self):
        root = self.start(queue_document())
        self.send(root, "retain until committed")
        main.schedule_once(timeout=1)
        with patch("main.commit_process", side_effect=RuntimeError("commit unavailable")):
            with self.assertRaisesRegex(RuntimeError, "commit unavailable"):
                main.schedule_once(timeout=1)
        self.assertEqual(self.queue(root), ["retain until committed"])

    def test_fenced_worker_cannot_consume_input(self):
        root = self.start(queue_document())
        self.send(root, "keep")
        claimed, acquired = repository.claim_process(self.redis, root["process_id"])
        self.assertTrue(acquired)
        stale = copy.deepcopy(claimed)
        stale.update(status="ready", execution_id="stale", _terminal_input_batch=["keep"])
        saved = repository.commit_process(self.redis, stale)
        self.assertEqual(saved["execution_id"], claimed["execution_id"])
        self.assertEqual(self.queue(root), ["keep"])

    def test_parent_and_child_with_shared_public_terminal_have_separate_buffers(self):
        self.documents["Child.flow"] = support.document("Child", wait=True)
        root = self.start(support.document("Root", child="Child.flow", wait=True))
        self.send(root, "parent input")
        self.drain()
        child = next(p for p in self.workflows() if p.get("parent_process_id") == root["process_id"])
        self.assertEqual(child["status"], "blocked")
        self.assertEqual(self.queue(child), [])
        self.assertEqual(self.queue(root), ["parent input"])
        self.send(root, "child input")
        self.assertEqual(self.queue(child), ["child input"])
        self.assertEqual(self.queue(root), ["parent input"])
        self.drain()
        self.assertEqual(main.read_process(root["process_id"])["status"], "completed")

    def test_termination_clears_buffer_and_late_events_do_not_recreate_it(self):
        root = self.start(queue_document())
        self.send(root, "pending")
        main.terminate_process(root["process_id"])
        self.assertEqual(self.queue(root), [])
        self.send(root, "too late")
        self.assertEqual(self.queue(root), [])

    def test_invalid_content_cannot_wake_or_buffer_input(self):
        root = self.start(queue_document())
        self.drain()
        for content in (None, "", "  ", 123):
            with self.subTest(content=content), self.assertRaises(ValueError):
                repository.enqueue_terminal_input(self.redis, root["terminal_id"], content)
        with self.assertLogs("main", level="WARNING"):
            main.handle_external_event(self.redis, json.dumps({"type": "terminal_message", "terminal_id": root["terminal_id"]}))
        self.assertEqual(self.queue(root), [])
        self.assertEqual(main.read_process(root["process_id"])["status"], "blocked")


class TerminalQueueMigrationTest(unittest.TestCase):
    def test_adjacent_wait_and_history_read_merge_preserving_data_edges(self):
        sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
        from migrate_terminal_queue_workflows import migrate_document
        doc = queue_document()
        doc["nodes"][1]["type"] = "read_terminal_input"
        doc["nodes"].insert(1, {"id": "wait", "type": "wait_terminal_event"})
        doc["connections"][0]["toId"] = "wait"
        doc["connections"].append(support.edge("wait", "read0"))
        original = copy.deepcopy(doc)
        converted = migrate_document(doc)
        self.assertEqual(doc, original)
        self.assertEqual(converted, queue_document())
        validate_workflow(converted)
        self.assertEqual(migrate_document(converted), converted)

    def test_history_cursor_is_rejected_instead_of_becoming_a_blocking_read(self):
        sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
        from migrate_terminal_queue_workflows import migrate_document
        doc = queue_document()
        doc["nodes"][1]["type"] = "read_terminal_input"
        doc["nodes"].append({"id": "cursor", "type": "list_length", "arguments": {"value_type": "list-content"}})
        doc["connections"].append(support.edge("read0", "cursor", "list-out", "list-in", "list-content"))
        with self.assertRaisesRegex(ValueError, "history cursors"):
            migrate_document(doc)

    def test_nonadjacent_wait_and_history_read_require_manual_rewiring(self):
        sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
        from migrate_terminal_queue_workflows import migrate_document
        doc = queue_document()
        doc["nodes"][1]["type"] = "read_terminal_input"
        doc["nodes"].append({"id": "wait", "type": "wait_terminal_event"})
        with self.assertRaisesRegex(ValueError, "nonadjacent"):
            migrate_document(doc)


if __name__ == "__main__":
    unittest.main()
