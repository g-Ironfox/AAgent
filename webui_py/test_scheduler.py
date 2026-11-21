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
from redis.exceptions import ConnectionError

from scheduler import ACTIVE_LIMIT, PROJECTION, PUBLIC_PROCESSES, PUBLIC_TABLES, create_scheduler_router


class SchedulerApiTest(unittest.TestCase):
    def setUp(self):
        self.logs = MagicMock()
        self.redis = MagicMock()
        self.pipe = self.redis.pipeline.return_value.__enter__.return_value
        self.app = FastAPI()
        self.app.include_router(create_scheduler_router(self.logs, self.redis))
        self.end = datetime.now(timezone.utc) - timedelta(seconds=5)
        self.start = self.end - timedelta(hours=1)
        self.logs.count_documents.return_value = 2
        self.logs.find.return_value.sort.return_value.limit.return_value = [
            {"_id": ObjectId(), "process_id": "finished", "status": "completed",
             "start_time": self.start, "finished_at": self.end},
        ]
        self.current = {
            "old-active": {"process_id": "old-active", "status": "blocked",
                           "start_time": (self.start - timedelta(days=10)).isoformat(),
                           "observed_at": self.end.isoformat(),
                           "wait_for": {"kind": "process_exit", "process_id": "child"}},
            "finished": {"process_id": "finished", "status": "completed"},
        }
        self.public_snapshot()

    def public_snapshot(self):
        self.pipe.execute.return_value = [
            {key: json.dumps(value) for key, value in self.current.items()},
            {"updated_at": self.end.isoformat()}, [], set(), {"old-active"}, set(),
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

    def test_current_processes_come_only_from_public_redis(self):
        response = self.get("/api/scheduler", params={"start": self.start.isoformat(), "end": self.end.isoformat(), "limit": 1})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["items"][0]["process_id"], "finished")
        self.assertNotIn("_id", data["items"][0])
        self.assertEqual(data["active_items"][0]["process_id"], "old-active")
        self.assertEqual(data["active_items"][0]["wait_for"]["process_id"], "child")
        self.assertTrue(data["history_truncated"])
        self.assertFalse(data["active_truncated"])
        self.assertEqual(data["active_count"], 1)
        self.assertEqual(data["status_counts"], {"blocked": 1})
        self.assertEqual(data["process_tables"]["blocked"], ["old-active"])
        self.assertEqual(data["current_source"], "public_redis")
        self.logs.find.assert_called_once_with({"start_time": {"$lte": self.end}, "$or": [{"finished_at": {"$gte": self.start}}, {"finished_at": None}]}, PROJECTION)
        self.logs.find.return_value.sort.return_value.limit.assert_called_once_with(1)
        self.assertNotIn("input", PROJECTION)
        self.redis.pipeline.assert_called_once_with(transaction=True)
        self.pipe.hgetall.assert_any_call(PUBLIC_PROCESSES)
        self.assertFalse(any(call.args and call.args[0] in {"processtable", "ready_processes", "blocked_processes"}
                             for call in self.pipe.method_calls))

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
        self.redis.pipeline.assert_not_called()

    def test_mongo_outage_does_not_hide_current_state(self):
        self.logs.count_documents.side_effect = ServerSelectionTimeoutError("offline")
        response = self.get("/api/scheduler")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["current_available"])
        self.assertFalse(data["history_available"])
        self.assertEqual(data["active_count"], 1)
        self.assertTrue(data["warnings"])

    def test_redis_outage_does_not_hide_history(self):
        self.pipe.execute.side_effect = ConnectionError("offline")
        data = self.get("/api/scheduler").json()
        self.assertFalse(data["current_available"])
        self.assertTrue(data["history_available"])
        self.assertTrue(data["warnings"])

    def test_both_sources_offline_returns_service_unavailable(self):
        self.logs.count_documents.side_effect = ServerSelectionTimeoutError("offline")
        self.pipe.execute.side_effect = ConnectionError("offline")
        self.assertEqual(self.get("/api/scheduler").status_code, 503)

    def test_empty_uninitialized_projection_is_not_reported_as_zero_processes(self):
        self.pipe.execute.return_value = [{}, {}, [], set(), set(), set()]
        data = self.get("/api/scheduler").json()
        self.assertFalse(data["current_available"])
        self.assertIn("not initialized", data["warnings"][0])

    def test_initialized_empty_projection_is_available(self):
        self.current = {}
        self.public_snapshot()
        data = self.get("/api/scheduler").json()
        self.assertTrue(data["current_available"])
        self.assertEqual(data["active_count"], 0)
        self.assertFalse(data["warnings"])

    def test_invalid_public_record_is_a_visible_projection_error(self):
        self.pipe.execute.return_value[0]["bad"] = "not json"
        data = self.get("/api/scheduler").json()
        self.assertFalse(data["current_available"])
        self.assertTrue(data["warnings"])

    def test_lost_history_is_final_and_keeps_the_discovery_finish_time(self):
        lost = {"process_id": "lost", "status": "lost", "start_time": self.start,
                "finished_at": self.end, "events": [{"event": "lost", "status": "lost"}]}
        self.logs.find.return_value.sort.return_value.limit.return_value = [lost]
        self.current["lost"] = {"process_id": "lost", "status": "lost"}
        self.public_snapshot()
        data = self.get("/api/scheduler").json()
        self.assertEqual(data["items"][0]["status"], "lost")
        self.assertEqual(datetime.fromisoformat(data["items"][0]["finished_at"]), self.end)
        self.assertNotIn("lost", [p["process_id"] for p in data["active_items"]])
        self.assertNotIn("lost", data["status_counts"])

    def test_current_counts_remain_complete_when_rows_are_truncated(self):
        self.current = {str(index): {"process_id": str(index), "status": "ready"} for index in range(ACTIVE_LIMIT + 1)}
        self.public_snapshot()
        self.pipe.execute.return_value[2] = list(self.current)
        data = self.get("/api/scheduler").json()
        self.assertTrue(data["active_truncated"])
        self.assertEqual(data["active_count"], ACTIVE_LIMIT + 1)
        self.assertEqual(data["status_counts"], {"ready": ACTIVE_LIMIT + 1})
        self.assertEqual(len(data["active_items"]), ACTIVE_LIMIT)
        self.assertEqual(data["process_tables"]["ready"], list(reversed(self.current)))
        self.pipe.lrange.assert_called_once_with(PUBLIC_TABLES["ready"], 0, -1)


if __name__ == "__main__":
    unittest.main()
