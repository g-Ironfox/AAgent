import json
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from bson import ObjectId
from pymongo import DESCENDING
from pymongo.errors import ServerSelectionTimeoutError

from terminal import TerminalRequest, create_terminal_router


class TerminalApiTest(unittest.TestCase):
    def setUp(self):
        self.redis = MagicMock()
        self.messages = MagicMock()
        router = create_terminal_router(self.redis, self.messages)
        self.sessions = next(route.endpoint for route in router.routes if route.path == "/api/terminal/sessions")
        self.history = next(route.endpoint for route in router.routes if route.path.endswith("/history"))
        self.submit = next(route.endpoint for route in router.routes if route.path == "/api/terminal")

    def test_history_reads_selected_terminal_in_chronological_order(self):
        now = datetime.now(timezone.utc)
        first = {"_id": ObjectId(), "role": "user", "content": "hello", "created_at": now}
        second = {
            "_id": ObjectId(), "role": "assistant", "content": "world",
            "created_at": now + timedelta(seconds=1),
        }
        self.messages.find.return_value.sort.return_value.limit.return_value = [second, first]
        result = self.history(2, "terminal-1")
        self.messages.find.assert_called_once_with({"terminal_process_id": "terminal-1"})
        self.messages.find.return_value.sort.assert_called_once_with(
            [("created_at", DESCENDING), ("_id", DESCENDING)]
        )
        self.messages.find.return_value.sort.return_value.limit.assert_called_once_with(2)
        self.assertEqual([item["content"] for item in result["items"]], ["hello", "world"])
        self.assertEqual(result["items"][0]["id"], str(first["_id"]))

    def test_terminal_sessions_lists_terminal_process_records(self):
        self.redis.hgetall.return_value = {
            "workflow-1": json.dumps({"process_id": "workflow-1", "process_type": "workflow"}),
            "terminal-1": json.dumps({
                "process_id": "terminal-1", "process_type": "terminal",
                "parent_process_id": "workflow-1", "status": "waiting_for_input",
                "start_time": "2026-11-17T00:00:00+00:00",
            }),
        }
        result = self.sessions()
        self.redis.hgetall.assert_called_once()
        self.assertEqual(result["sessions"], [{
            "terminal_process_id": "terminal-1", "parent_process_id": "workflow-1",
            "status": "waiting_for_input", "start_time": "2026-11-17T00:00:00+00:00",
            "workflow_name": None, "workflow_status": None,
            "workflow_parent_process_id": None, "root_process_id": None, "wait_for": None,
        }])

    def test_send_persists_message_only_to_selected_terminal(self):
        self.redis.hget.return_value = json.dumps({
            "process_id": "terminal-1", "process_type": "terminal",
            "status": "waiting_for_input",
        })
        result = self.submit(TerminalRequest(
            content="  hello  ", terminal_process_id="terminal-1"
        ))
        document = self.messages.insert_one.call_args.args[0]
        self.assertEqual(document["role"], "user")
        self.assertEqual(document["content"], "hello")
        self.assertEqual(document["terminal_process_id"], "terminal-1")
        self.assertEqual(result["message"]["id"], str(document["_id"]))
        self.assertEqual(result["message"]["created_at"], document["created_at"])
        self.assertNotIn("event", result)
        self.redis.rpush.assert_not_called()

    def test_terminal_session_exposes_child_workflow_and_wait_state(self):
        self.redis.hgetall.return_value = {
            "root": json.dumps({"process_id": "root", "process_type": "workflow"}),
            "child": json.dumps({
                "process_id": "child", "process_type": "workflow",
                "root_process_id": "root", "parent_process_id": "root",
                "workflow_name": "Child.flow", "status": "blocked",
                "wait_for": {"kind": "terminal_message", "process_id": "terminal-child"},
            }),
            "terminal-child": json.dumps({
                "process_id": "terminal-child", "process_type": "terminal",
                "parent_process_id": "child", "status": "waiting_for_input",
                "start_time": "2026-11-17T00:00:00+00:00",
            }),
        }
        session = self.sessions()["sessions"][0]
        self.assertEqual(session["workflow_name"], "Child.flow")
        self.assertEqual(session["workflow_parent_process_id"], "root")
        self.assertEqual(session["root_process_id"], "root")
        self.assertEqual(session["workflow_status"], "blocked")
        self.assertEqual(session["wait_for"]["kind"], "terminal_message")

    @patch("terminal.wake_process")
    def test_saved_message_wakes_only_its_own_terminal_parent(self, wake):
        self.redis.hget.return_value = json.dumps({
            "process_id": "terminal-child", "process_type": "terminal",
            "parent_process_id": "child", "status": "waiting_for_input",
        })
        self.submit(TerminalRequest(content="continue", terminal_process_id="terminal-child"))
        self.messages.insert_one.assert_called_once()
        wake.assert_called_once_with(self.redis, "child", "terminal-child", "terminal_message")

    @patch("terminal.wake_process")
    def test_failed_message_storage_never_wakes_process(self, wake):
        self.redis.hget.return_value = json.dumps({
            "process_id": "terminal-child", "process_type": "terminal",
            "parent_process_id": "child", "status": "waiting_for_input",
        })
        self.messages.insert_one.side_effect = ServerSelectionTimeoutError("offline")
        result = self.submit(TerminalRequest(content="continue", terminal_process_id="terminal-child"))
        self.assertEqual(result.status_code, 503)
        wake.assert_not_called()

    @patch("terminal.wake_process", side_effect=KeyError("parent missing"))
    def test_wakeup_failure_reports_saved_message(self, wake):
        self.redis.hget.return_value = json.dumps({
            "process_id": "terminal-child", "process_type": "terminal",
            "parent_process_id": "child", "status": "waiting_for_input",
        })
        with self.assertLogs("terminal", level="ERROR"):
            result = self.submit(TerminalRequest(content="continue", terminal_process_id="terminal-child"))
        self.assertEqual(result.status_code, 503)
        body = json.loads(result.body)
        self.assertIn("已保存", body["error"])
        self.assertEqual(body["message"]["content"], "continue")

    def test_send_rejects_terminated_terminal(self):
        self.redis.hget.return_value = json.dumps({
            "process_id": "terminal-1", "process_type": "terminal", "status": "terminated",
        })
        result = self.submit(TerminalRequest(
            content="hello", terminal_process_id="terminal-1"
        ))
        self.assertEqual(result.status_code, 409)
        self.messages.insert_one.assert_not_called()

    def test_send_rejects_missing_or_non_terminal_process(self):
        self.redis.hget.return_value = None
        missing = self.submit(TerminalRequest(content="hello", terminal_process_id="missing"))
        self.assertEqual(missing.status_code, 404)
        self.redis.hget.return_value = json.dumps({
            "process_id": "workflow-1", "process_type": "workflow",
        })
        wrong_type = self.submit(TerminalRequest(content="hello", terminal_process_id="workflow-1"))
        self.assertEqual(wrong_type.status_code, 404)
        self.messages.insert_one.assert_not_called()

    def test_storage_failure_reports_unavailable(self):
        self.redis.hget.return_value = json.dumps({
            "process_id": "terminal-1", "process_type": "terminal",
            "status": "waiting_for_input",
        })
        self.messages.insert_one.side_effect = ServerSelectionTimeoutError("offline")
        result = self.submit(TerminalRequest(
            content="hello", terminal_process_id="terminal-1"
        ))
        self.assertEqual(result.status_code, 503)
        self.redis.rpush.assert_not_called()

    def test_history_storage_failure_is_reported(self):
        self.messages.find.side_effect = ServerSelectionTimeoutError("offline")
        self.assertEqual(self.history(10, "terminal-1").status_code, 503)

    def test_invalid_inputs_are_rejected_before_storage(self):
        for payload in (
            TerminalRequest(content="  ", terminal_process_id="terminal-1"),
            TerminalRequest(content="a" * 4001, terminal_process_id="terminal-1"),
            TerminalRequest(content="hello", files=["file"], terminal_process_id="terminal-1"),
        ):
            with self.subTest(payload=payload):
                self.assertEqual(self.submit(payload).status_code, 400)
        for limit in (0, 301):
            self.assertEqual(self.history(limit, "terminal-1").status_code, 400)
        self.messages.insert_one.assert_not_called()
        self.messages.find.assert_not_called()


if __name__ == "__main__":
    unittest.main()
