import json
import unittest
from unittest.mock import MagicMock

from fastapi.responses import JSONResponse
from file_store import FileMissingError
from processes import CreateProcessRequest, create_processes_router
from redis.exceptions import ConnectionError as RedisConnectionError


class ProcessCreationApiTest(unittest.TestCase):
    def setUp(self):
        self.redis = MagicMock()
        self.store = MagicMock()
        router = create_processes_router(self.redis, self.store)
        self.create = next(route.endpoint for route in router.routes if route.path == "/api/processes")
        self.workflow_options = next(
            route.endpoint for route in router.routes
            if route.path == "/api/processes/workflow-options"
        )

    def test_workflow_options_are_listed_from_valid_files(self):
        self.store.list_files.return_value = [{"file_id": "file-1", "name": "demo.json"}]
        self.store.get_file.return_value = {
            "file_id": "file-1",
            "name": "demo.json",
            "content": json.dumps({
                "schema_version": "2.0",
                "input_ports": [],
                "output_ports": [],
                "nodes": [],
                "connections": [],
            }),
        }

        result = self.workflow_options()

        self.assertEqual(result["items"][0]["file_id"], "file-1")

    def test_creation_queues_raw_workflow_and_only_returns_public_identity(self):
        content = '{"schema_version":"2.0","nodes":[]}'
        self.store.get_file.return_value = {"name": "demo.flow", "content": content}

        result = self.create(CreateProcessRequest(
            workflow_file_id="file1",
            terminal_id="frontend-terminal",
            inputs={"text": "hello"},
        ))

        self.redis.lpush.assert_called_once()
        queue_name, raw_event = self.redis.lpush.call_args.args
        self.assertEqual(queue_name, "external_events")
        event = json.loads(raw_event)
        self.assertEqual(event, {
            "type": "create_process",
            "workflow_content": content,
            "workflow_file_id": "file1",
            "workflow_name": "demo.flow",
            "workflow_permissions": {
                "runtime": {"read": 0, "write": 0},
                "required": {"read": 0, "write": 0},
            },
            "inputs": {"text": "hello"},
            "terminal_id": "frontend-terminal",
        })
        self.assertEqual(result, {
            "status": "queued",
            "terminal_id": "frontend-terminal",
            "workflow_name": "demo.flow",
        })
        self.assertNotIn("process_id", result)

    def test_invalid_workflow_payload_does_not_queue(self):
        self.store.get_file.return_value = {"name": "demo.flow", "content": "[]"}

        result = self.create(CreateProcessRequest(
            workflow_file_id="file1", terminal_id="frontend-terminal"
        ))

        self.assertIsInstance(result, JSONResponse)
        self.assertEqual(result.status_code, 400)
        self.redis.lpush.assert_not_called()

    def test_missing_workflow_returns_not_found(self):
        self.store.get_file.side_effect = FileMissingError("missing")

        result = self.create(CreateProcessRequest(
            workflow_file_id="file1", terminal_id="frontend-terminal"
        ))

        self.assertEqual(result.status_code, 404)
        self.redis.lpush.assert_not_called()

    def test_queue_failure_returns_service_unavailable(self):
        self.store.get_file.return_value = {"name": "demo.flow", "content": "{}"}
        self.redis.lpush.side_effect = RedisConnectionError("offline")

        result = self.create(CreateProcessRequest(
            workflow_file_id="file1", terminal_id="frontend-terminal"
        ))

        self.assertEqual(result.status_code, 503)


if __name__ == "__main__":
    unittest.main()
