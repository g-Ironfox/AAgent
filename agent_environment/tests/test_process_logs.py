import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock

from bson import ObjectId
from fastapi.encoders import jsonable_encoder
from pymongo.errors import ServerSelectionTimeoutError

from process_logs import create_process_logs_router


class ProcessLogsApiTest(unittest.TestCase):
    def setUp(self):
        self.logs = MagicMock()
        router = create_process_logs_router(self.logs)
        self.endpoint = next(route.endpoint for route in router.routes if route.path == "/api/process-logs")

    def test_lists_live_processes_with_identity_waits_and_events(self):
        document = {
            "_id": ObjectId(), "process_id": "child", "parent_process_id": "parent",
            "root_process_id": "root", "process_type": "workflow", "status": "blocked",
            "start_time": datetime(2026, 11, 19, tzinfo=timezone.utc),
            "wait_for": {"kind": "terminal_message", "process_id": "terminal"},
            "events": [{"event": "blocked", "timestamp": "2026-11-19T00:00:00+00:00"}],
            "nodes": [{"child_process_id": "grandchild", "status": "waiting"}],
            "input": {"text": "hello"}, "output": {},
        }
        self.logs.find.return_value.sort.return_value.limit.return_value = [document]

        result = jsonable_encoder(self.endpoint(50))

        item = result["items"][0]
        self.assertEqual(item["id"], str(document["_id"]))
        self.assertNotIn("_id", item)
        self.assertEqual(item["process_id"], "child")
        self.assertEqual(item["parent_process_id"], "parent")
        self.assertEqual(item["wait_for"], document["wait_for"])
        self.assertEqual(item["events"], document["events"])
        self.assertEqual(item["nodes"][0]["child_process_id"], "grandchild")
        self.assertTrue(item["start_time"].startswith("2026-11-19"))
        self.assertIn("_id", document)
        self.logs.find.assert_called_once_with({})
        self.logs.find.return_value.sort.assert_called_once_with("_id", -1)
        self.logs.find.return_value.sort.return_value.limit.assert_called_once_with(50)

    def test_database_outage_returns_service_unavailable(self):
        self.logs.find.side_effect = ServerSelectionTimeoutError("offline")
        response = self.endpoint(200)
        self.assertEqual(response.status_code, 503)
        self.assertIn(b"process logs", response.body)



if __name__ == "__main__":
    unittest.main()
