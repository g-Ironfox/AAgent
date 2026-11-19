import asyncio
import json
import unittest
from types import SimpleNamespace
from urllib.parse import urlencode
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from bson import ObjectId
from fastapi import FastAPI
from pymongo.errors import ServerSelectionTimeoutError

from scheduler import ACTIVE_LIMIT, PROJECTION, create_scheduler_router


class SchedulerApiTest(unittest.TestCase):
    def setUp(self):
        self.logs = MagicMock()
        self.app = FastAPI()
        self.app.include_router(create_scheduler_router(self.logs))
        self.end = datetime.now(timezone.utc) - timedelta(seconds=5)
        self.start = self.end - timedelta(hours=1)
        self.logs.count_documents.side_effect = [2, 1]
        self.logs.find.return_value.sort.return_value.limit.side_effect = [
            [{"_id": ObjectId(), "process_id": "finished", "status": "completed",
              "start_time": self.start, "finished_at": self.end}],
            [{"_id": ObjectId(), "process_id": "old-active", "status": "blocked",
              "start_time": self.start - timedelta(days=10), "events": [],
              "wait_for": {"kind": "process_exit", "process_id": "child"}}],
        ]

    def get(self, path, params=None):
        async def request():
            messages = []
            async def receive():
                return {"type": "http.request", "body": b"", "more_body": False}
            async def send(message):
                messages.append(message)
            await self.app({"type": "http", "method": "GET", "path": path,
                            "query_string": urlencode(params or {}).encode(),
                            "headers": [], "scheme": "http", "root_path": ""},
                           receive, send)
            status = next(m["status"] for m in messages if m["type"] == "http.response.start")
            body = b"".join(m.get("body", b"") for m in messages if m["type"] == "http.response.body")
            return SimpleNamespace(status_code=status, json=lambda: json.loads(body))
        return asyncio.run(request())

    def test_snapshot_keeps_current_processes_independent_of_history_window(self):
        response = self.get("/api/scheduler", params={"start": self.start.isoformat(), "end": self.end.isoformat(), "limit": 1})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["items"][0]["process_id"], "finished")
        self.assertNotIn("_id", data["items"][0])
        self.assertEqual(data["active_items"][0]["process_id"], "old-active")
        self.assertEqual(data["active_items"][0]["wait_for"]["process_id"], "child")
        self.assertTrue(data["history_truncated"])
        self.assertFalse(data["active_truncated"])
        history_query = self.logs.find.call_args_list[0].args[0]
        self.assertEqual(history_query, {"start_time": {"$lte": self.end}, "$or": [{"finished_at": {"$gte": self.start}}, {"finished_at": None}]})
        active_query = self.logs.find.call_args_list[1].args[0]
        self.assertEqual(active_query, {"status": {"$nin": ["completed", "failed", "terminated"]}})
        self.assertNotIn("input", PROJECTION)
        self.assertNotIn("nodes", PROJECTION)
        self.assertEqual(self.logs.find.return_value.sort.return_value.limit.call_args_list[1].args, (ACTIVE_LIMIT,))

    def test_defaults_to_last_fifteen_minutes(self):
        data = self.get("/api/scheduler").json()
        self.assertAlmostEqual((datetime.fromisoformat(data["end"]) - datetime.fromisoformat(data["start"])).total_seconds(), 900)

    def test_rejects_invalid_ranges_and_limits_without_database_calls(self):
        for params in [
            {"start": self.end.isoformat(), "end": self.start.isoformat()},
            {"start": (self.end - timedelta(days=8)).isoformat(), "end": self.end.isoformat()},
            {"start": "2026-01-01T00:00:00"},
            {"end": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()},
            {"start": "bad-time"}, {"limit": 0}, {"limit": 1001},
        ]:
            with self.subTest(params=params):
                self.assertEqual(self.get("/api/scheduler", params=params).status_code, 422)
        self.logs.find.assert_not_called()
        self.logs.count_documents.assert_not_called()

    def test_outage_is_a_service_unavailable_response(self):
        self.logs.count_documents.side_effect = ServerSelectionTimeoutError("offline")
        response = self.get("/api/scheduler")
        self.assertEqual(response.status_code, 503)
        self.assertIn("unavailable", response.json()["error"])

    def test_reports_current_table_truncation(self):
        self.logs.count_documents.side_effect = [0, ACTIVE_LIMIT + 1]
        self.logs.find.return_value.sort.return_value.limit.side_effect = [[], []]
        data = self.get("/api/scheduler").json()
        self.assertTrue(data["active_truncated"])
        self.assertEqual(data["active_count"], ACTIVE_LIMIT + 1)


if __name__ == "__main__":
    unittest.main()
