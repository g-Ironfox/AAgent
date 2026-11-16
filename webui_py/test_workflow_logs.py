import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock

from bson import ObjectId
from pymongo.errors import ServerSelectionTimeoutError

from workflow_logs import create_workflow_logs_router


class WorkflowLogsApiTest(unittest.TestCase):
    def setUp(self):
        self.logs = MagicMock()
        router = create_workflow_logs_router(self.logs)
        self.endpoint = next(route.endpoint for route in router.routes if route.path == "/api/workflow-logs")

    def test_lists_latest_runs_and_converts_document_id(self):
        run_id = ObjectId()
        started_at = datetime.now(timezone.utc)
        self.logs.find.return_value.sort.return_value.limit.return_value = [{
            "_id": run_id, "workflow_name": "demo", "started_at": started_at,
            "input": {"query": "hello"}, "output": {"content": "world"},
        }]

        result = self.endpoint(200)

        self.logs.find.assert_called_once_with({})
        self.logs.find.return_value.sort.assert_called_once_with("_id", -1)
        self.logs.find.return_value.sort.return_value.limit.assert_called_once_with(200)
        self.assertEqual(result["items"][0]["id"], str(run_id))
        self.assertEqual(result["items"][0]["input"], {"query": "hello"})
        self.assertEqual(result["items"][0]["output"], {"content": "world"})

    def test_database_outage_returns_service_unavailable(self):
        self.logs.find.side_effect = ServerSelectionTimeoutError("offline")
        response = self.endpoint()
        self.assertEqual(response.status_code, 503)


if __name__ == "__main__":
    unittest.main()
