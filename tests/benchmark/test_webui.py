"""ASGI API tests without an HTTP client dependency or live services."""
import asyncio
import json
import unittest
from unittest.mock import Mock
from urllib.parse import urlsplit
import importlib.util
if importlib.util.find_spec("fastapi") is None:
    raise unittest.SkipTest("FastAPI is only installed in benchmark_webui")
from redis.exceptions import RedisError
from benchmark_common.models import JobConfig
from benchmark_common.store import now
from benchmark_webui.main import create_app


def request(app, method, path, body=None):
    async def run():
        parsed = urlsplit(path)
        payload = json.dumps(body).encode() if body is not None else b""
        scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
                 "method": method, "scheme": "http", "path": parsed.path, "raw_path": parsed.path.encode(),
                 "query_string": parsed.query.encode(), "root_path": "",
                 "headers": [(b"content-type", b"application/json")], "server": ("test", 80), "client": ("test", 123)}
        messages = []
        async def receive():
            return {"type": "http.request", "body": payload, "more_body": False}
        async def send(message):
            messages.append(message)
        await app(scope, receive, send)
        status = next(item["status"] for item in messages if item["type"] == "http.response.start")
        data = b"".join(item.get("body", b"") for item in messages if item["type"] == "http.response.body")
        return status, json.loads(data)
    return asyncio.run(run())


class WebUITests(unittest.TestCase):
    def setUp(self):
        self.store = Mock()
        config = JobConfig(workflow_file_id="flow").model_dump()
        self.job = {"job_id": "a" * 32, "status": "queued", "config": config}
        self.store.create.return_value = self.job
        self.store.get.return_value = self.job
        self.app = create_app(self.store, upstream=lambda: {"items": [{"file_id": "flow", "name": "Agent"}]})
        self.app.state.store = self.store

    def test_stopped_threads_are_offline_without_waiting_for_timeout(self):
        stamp = now()
        self.store.workers.find.return_value.sort.return_value.limit.return_value = [
            {"worker_id": "active", "instance_id": "container", "slot": 1, "last_seen": stamp},
            {"worker_id": "stopped", "instance_id": "old", "slot": 1,
             "last_seen": stamp, "stopped_at": stamp}]
        status, data = request(self.app, "GET", "/api/options")
        self.assertEqual(status, 200)
        self.assertEqual([worker["online"] for worker in data["workers"]], [True, False])

    def test_publish_survives_redis_outage(self):
        self.store.dispatch.side_effect = RedisError("offline")
        with self.assertLogs("benchmark_webui", level="ERROR"):
            status, data = request(self.app, "POST", "/api/jobs", {"workflow_file_id": "flow"})
        self.assertEqual(status, 202)
        self.assertEqual(data["status"], "queued")
        self.store.create.assert_called_once()
        self.store.dispatch.assert_called_once()

    def test_unknown_workflow_cannot_publish(self):
        status, data = request(self.app, "POST", "/api/jobs", {"workflow_file_id": "unknown"})
        self.assertEqual(status, 400)
        self.store.create.assert_not_called()

    def test_empty_event_poll_preserves_cursor(self):
        self.store.events.find.return_value.sort.return_value.limit.return_value = []
        status, data = request(self.app, "GET", "/api/jobs/id/events?after=19&episode=2")
        self.assertEqual(status, 200)
        self.assertEqual(data, {"items": [], "next_cursor": 19, "has_more": False})
        self.store.events.find.assert_called_once_with({"job_id": "id", "seq": {"$gt": 19}, "episode_index": 2})

    def test_missing_job_and_invalid_cursor(self):
        self.store.get.return_value = None
        self.assertEqual(request(self.app, "GET", "/api/jobs/missing")[0], 404)
        self.assertEqual(request(self.app, "GET", "/api/jobs/id/events?after=-1")[0], 422)

    def test_invalid_config_is_rejected_before_persistence(self):
        status, data = request(self.app, "POST", "/api/jobs", {"workflow_file_id": "flow", "episodes": True})
        self.assertEqual(status, 422)
        self.store.create.assert_not_called()


if __name__ == "__main__":
    unittest.main()
