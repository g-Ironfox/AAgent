import json
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from bson import ObjectId
from pymongo import DESCENDING
from pymongo.errors import ServerSelectionTimeoutError
from redis.exceptions import RedisError

from terminal import TerminalRequest, create_terminal_router


class TerminalApiTest(unittest.TestCase):
    def setUp(self):
        self.redis = MagicMock()
        self.messages = MagicMock()
        router = create_terminal_router(self.redis, self.messages)
        self.sessions = next(route.endpoint for route in router.routes if route.path == "/api/terminal/sessions")
        self.history = next(route.endpoint for route in router.routes if route.path.endswith("/history"))
        self.submit = next(route.endpoint for route in router.routes if route.path == "/api/terminal")

    def test_history_reads_public_terminal_id(self):
        now = datetime.now(timezone.utc)
        first = {"_id": ObjectId(), "role": "user", "content": "hello", "created_at": now}
        second = {"_id": ObjectId(), "role": "assistant", "content": "world", "created_at": now + timedelta(seconds=1)}
        self.messages.find.return_value.sort.return_value.limit.return_value = [second, first]

        result = self.history(2, "terminal-1")

        self.messages.find.assert_called_once_with({"terminal_id": "terminal-1"})
        self.messages.find.return_value.sort.assert_called_once_with(
            [("created_at", DESCENDING), ("_id", DESCENDING)]
        )
        self.assertEqual([item["content"] for item in result["items"]], ["hello", "world"])
        self.assertNotIn("terminal_process_id", result["items"][0])

    def test_sessions_read_only_public_terminal_hash(self):
        self.redis.hgetall.return_value = {
            "public-terminal": json.dumps({
                "terminal_id": "public-terminal", "status": "open",
                "start_time": "2026-11-17T00:00:00+00:00", "closed_at": None,
                "workflow_name": "demo.flow", "workflow_status": "blocked",
                "wait_kind": "terminal_message",
                "process_id": "must-not-be-exposed",
            }),
        }
        session = self.sessions()["sessions"][0]
        self.redis.hgetall.assert_called_once_with("terminal_sessions")
        self.assertEqual(session, {
            "terminal_id": "public-terminal", "status": "open",
            "start_time": "2026-11-17T00:00:00+00:00", "closed_at": None,
            "workflow_name": "demo.flow", "workflow_status": "blocked",
            "wait_kind": "terminal_message",
        })

    def test_sessions_keep_closed_records_and_skip_invalid_records(self):
        self.redis.hgetall.return_value = {
            "old": json.dumps({"terminal_id": "old", "status": "closed",
                               "start_time": "2026-11-17", "closed_at": "2026-11-18"}),
            "new": json.dumps({"terminal_id": "new", "status": "open",
                               "start_time": "2026-11-19"}),
            "broken": "not json",
            "wrong-id": json.dumps({"terminal_id": "another", "status": "open"}),
            "wrong-status": json.dumps({"terminal_id": "wrong-status", "status": "terminated"}),
        }
        sessions = self.sessions()["sessions"]
        self.assertEqual([session["terminal_id"] for session in sessions], ["new", "old"])
        self.assertEqual(sessions[1]["status"], "closed")
        self.assertEqual(sessions[1]["closed_at"], "2026-11-18")

    def test_send_saves_and_queues_by_public_terminal_id(self):
        result = self.submit(TerminalRequest(content="  hello  ", terminal_id="public-terminal"))

        document = self.messages.insert_one.call_args.args[0]
        self.assertEqual(document["terminal_id"], "public-terminal")
        self.redis.lpush.assert_called_once()
        queue_name, raw_event = self.redis.lpush.call_args.args
        self.assertEqual(queue_name, "external_events")
        self.assertEqual(json.loads(raw_event), {
            "type": "terminal_message", "terminal_id": "public-terminal"
        })
        self.assertEqual(result["message"]["id"], str(document["_id"]))
        self.assertNotIn("process_id", result)

    def test_unknown_terminal_is_still_saved_and_queued(self):
        result = self.submit(TerminalRequest(content="hello", terminal_id="not-yet-created"))

        self.assertEqual(result["message"]["terminal_id"], "not-yet-created")
        self.messages.insert_one.assert_called_once()
        self.redis.lpush.assert_called_once()

    def test_storage_failure_prevents_queueing(self):
        self.messages.insert_one.side_effect = ServerSelectionTimeoutError("offline")

        result = self.submit(TerminalRequest(content="hello", terminal_id="terminal-1"))

        self.assertEqual(result.status_code, 503)
        self.redis.lpush.assert_not_called()

    def test_queue_failure_reports_saved_message(self):
        self.redis.lpush.side_effect = RedisError("offline")

        result = self.submit(TerminalRequest(content="hello", terminal_id="terminal-1"))

        self.assertEqual(result.status_code, 503)
        body = json.loads(result.body)
        self.assertIn("event queueing failed", body["error"])
        self.assertEqual(body["message"]["content"], "hello")

    def test_invalid_inputs_are_rejected_before_storage(self):
        for payload in (
            TerminalRequest(content="  ", terminal_id="terminal-1"),
            TerminalRequest(content="a" * 4001, terminal_id="terminal-1"),
            TerminalRequest(content="hello", files=["file"], terminal_id="terminal-1"),
        ):
            with self.subTest(payload=payload):
                self.assertEqual(self.submit(payload).status_code, 400)
        for limit in (0, 301):
            self.assertEqual(self.history(limit, "terminal-1").status_code, 400)
        self.messages.insert_one.assert_not_called()


if __name__ == "__main__":
    unittest.main()
