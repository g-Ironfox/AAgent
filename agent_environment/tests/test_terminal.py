import json
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from bson import ObjectId
from pymongo import ASCENDING, DESCENDING
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
        self.output = next(route.endpoint for route in router.routes if route.path.endswith("/output"))
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
            "type": "terminal_message", "terminal_id": "public-terminal", "content": "hello"
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

    def test_large_observation_is_saved_and_queued_without_truncation(self):
        content = json.dumps({"type": "observation", "text": "observation " * 5000})
        result = self.submit(TerminalRequest(content=content, terminal_id="terminal-1"))

        self.assertEqual(result["message"]["content"], content)
        self.assertEqual(self.messages.insert_one.call_args.args[0]["content"], content)
        event = json.loads(self.redis.lpush.call_args.args[1])
        self.assertEqual(event["content"], content)

    def test_output_reads_oldest_assistant_messages_for_one_terminal(self):
        now = datetime.now(timezone.utc)
        documents = [
            {"_id": ObjectId(), "role": "assistant", "content": action, "created_at": now}
            for action in ("look", "inventory")
        ]
        self.messages.find.return_value.sort.return_value.limit.return_value = documents

        result = self.output("terminal-1", 2)

        self.messages.find.assert_called_once_with({"terminal_id": "terminal-1", "role": "assistant"})
        self.messages.find.return_value.sort.assert_called_once_with([("_id", ASCENDING)])
        self.messages.find.return_value.sort.return_value.limit.assert_called_once_with(2)
        self.assertEqual([item["content"] for item in result["items"]], ["look", "inventory"])
        self.assertEqual(result["next_cursor"], str(documents[-1]["_id"]))

    def test_output_cursor_excludes_already_read_messages(self):
        cursor = str(ObjectId())
        document = {"_id": ObjectId(), "role": "assistant", "content": "look",
                    "created_at": datetime.now(timezone.utc)}
        self.messages.find.return_value.sort.return_value.limit.return_value = [document]

        result = self.output("terminal-1", 150, cursor)

        self.messages.find.assert_called_once_with({
            "terminal_id": "terminal-1", "role": "assistant", "_id": {"$gt": ObjectId(cursor)},
        })
        self.assertEqual(result["next_cursor"], str(document["_id"]))

    def test_empty_output_preserves_cursor_for_the_next_poll(self):
        self.messages.find.return_value.sort.return_value.limit.return_value = []
        for cursor in (None, str(ObjectId())):
            with self.subTest(cursor=cursor):
                result = self.output("terminal-1", 150, cursor)
                self.assertEqual(result["items"], [])
                self.assertEqual(result["next_cursor"], cursor)

    def test_invalid_output_parameters_do_not_read_storage(self):
        for cursor in ("", "not-an-id", "z" * 24):
            with self.subTest(cursor=cursor):
                self.assertEqual(self.output("terminal-1", 150, cursor).status_code, 400)
        for limit in (0, 301):
            self.assertEqual(self.output("terminal-1", limit).status_code, 400)
        self.messages.find.assert_not_called()

    def test_output_storage_failure_returns_unavailable(self):
        self.messages.find.side_effect = ServerSelectionTimeoutError("offline")

        result = self.output("terminal-1", 150)

        self.assertEqual(result.status_code, 503)
        self.assertEqual(json.loads(result.body)["error"], "terminal output unavailable")

    def test_invalid_inputs_are_rejected_before_storage(self):
        for payload in (
            TerminalRequest(content="  ", terminal_id="terminal-1"),
            TerminalRequest(content="hello", files=["file"], terminal_id="terminal-1"),
        ):
            with self.subTest(payload=payload):
                self.assertEqual(self.submit(payload).status_code, 400)
        for limit in (0, 301):
            self.assertEqual(self.history(limit, "terminal-1").status_code, 400)
        self.messages.insert_one.assert_not_called()


class TerminalBodyLimitTest(unittest.IsolatedAsyncioTestCase):
    async def test_terminal_entrypoint_accepts_large_requests_and_rejects_over_one_mib(self):
        # Exercise the actual entrypoint guard; no external services are needed.
        with patch("pymongo.MongoClient"), patch("redis.Redis.from_url"), patch("file_store.FileStore"):
            from main import request_body_guard
        from starlette.requests import Request
        from starlette.responses import Response

        for size, expected_status in ((60_000, 204), (1024 * 1024, 204), (1024 * 1024 + 1, 400)):
            with self.subTest(size=size):
                request = Request({
                    "type": "http", "method": "POST", "path": "/api/terminal",
                    "headers": [(b"content-length", str(size).encode("ascii"))],
                })
                call_next = AsyncMock(return_value=Response(status_code=204))

                result = await request_body_guard(request, call_next)

                self.assertEqual(result.status_code, expected_status)
                if expected_status == 204:
                    call_next.assert_awaited_once_with(request)
                else:
                    call_next.assert_not_awaited()
                    self.assertIn("1 MiB", json.loads(result.body)["error"])


if __name__ == "__main__":
    unittest.main()
