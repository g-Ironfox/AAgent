import json
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import redis
from bson import ObjectId
from pymongo import DESCENDING
from pymongo.errors import ServerSelectionTimeoutError

from terminal import TerminalRequest, create_terminal_router


class TerminalApiTest(unittest.TestCase):
    def setUp(self):
        self.queue = MagicMock()
        self.messages = MagicMock()
        router = create_terminal_router(self.queue, self.messages, "test_queue")
        self.history = next(route.endpoint for route in router.routes if route.path.endswith("/history"))
        self.submit = next(route.endpoint for route in router.routes if route.path == "/api/terminal")

    def test_history_reads_messages_in_chronological_order_without_event_filter(self):
        now = datetime.now(timezone.utc)
        first = {"_id": ObjectId(), "role": "user", "content": "hello", "created_at": now}
        second = {
            "_id": ObjectId(), "role": "assistant", "content": "world",
            "created_at": now + timedelta(seconds=1),
        }
        self.messages.find.return_value.sort.return_value.limit.return_value = [second, first]
        result = self.history(2)
        self.messages.find.assert_called_once_with({})
        self.messages.find.return_value.sort.assert_called_once_with(
            [("created_at", DESCENDING), ("_id", DESCENDING)]
        )
        self.messages.find.return_value.sort.return_value.limit.assert_called_once_with(2)
        self.assertEqual([item["content"] for item in result["items"]], ["hello", "world"])
        self.assertEqual(result["items"][0]["id"], str(first["_id"]))
        self.assertNotIn("event", result["items"][1])

    def test_send_persists_input_and_preserves_priority_event_queue(self):
        self.queue.rpush.side_effect = lambda *args: self.messages.insert_one.assert_called_once()
        result = self.submit(TerminalRequest(content="  你好  "))
        document = self.messages.insert_one.call_args.args[0]
        self.assertEqual(document["role"], "user")
        self.assertEqual(document["content"], "你好")
        self.assertNotIn("event_type", document)
        self.assertEqual(result["message"]["id"], str(document["_id"]))
        self.assertEqual(result["message"]["created_at"], document["created_at"])
        queue, serialized = self.queue.rpush.call_args.args
        self.assertEqual(queue, "test_queue")
        event = json.loads(serialized)
        self.assertEqual(event, result["event"])
        self.assertEqual(event["version"], "1.1")
        self.assertEqual(event["event_type"], "terminal")
        self.assertEqual(event["payload"], {"content": "你好", "files": []})
        self.messages.delete_one.assert_not_called()

    def test_storage_failure_does_not_queue_command(self):
        self.messages.insert_one.side_effect = ServerSelectionTimeoutError("offline")
        result = self.submit(TerminalRequest(content="hello"))
        self.assertEqual(result.status_code, 503)
        self.queue.rpush.assert_not_called()

    def test_queue_failure_removes_unsent_input(self):
        self.queue.rpush.side_effect = redis.ConnectionError("offline")
        result = self.submit(TerminalRequest(content="hello"))
        self.assertEqual(result.status_code, 503)
        document = self.messages.insert_one.call_args.args[0]
        self.messages.delete_one.assert_called_once_with({"_id": document["_id"]})

    def test_cleanup_failure_returns_queue_error_and_logs_failure(self):
        self.queue.rpush.side_effect = redis.ConnectionError("offline")
        self.messages.delete_one.side_effect = ServerSelectionTimeoutError("offline")
        with self.assertLogs("terminal", level="ERROR"):
            result = self.submit(TerminalRequest(content="hello"))
        self.assertEqual(result.status_code, 503)

    def test_history_storage_failure_is_reported(self):
        self.messages.find.side_effect = ServerSelectionTimeoutError("offline")
        self.assertEqual(self.history(10).status_code, 503)

    def test_invalid_inputs_are_rejected_before_storage_or_queue(self):
        for payload in (
            TerminalRequest(content="  "), TerminalRequest(content="a" * 4001),
            TerminalRequest(content="hello", files=["file"]),
        ):
            with self.subTest(payload=payload):
                self.assertEqual(self.submit(payload).status_code, 400)
        for limit in (0, 301):
            self.assertEqual(self.history(limit).status_code, 400)
        self.messages.insert_one.assert_not_called()
        self.messages.find.assert_not_called()
        self.queue.rpush.assert_not_called()


if __name__ == "__main__":
    unittest.main()
