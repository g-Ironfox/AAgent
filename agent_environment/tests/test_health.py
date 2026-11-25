"""Readiness must check storage without depending on a running executor."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import Mock, PropertyMock, patch

from pymongo.errors import ServerSelectionTimeoutError
from redis.exceptions import ConnectionError
from file_store import FileStoreUnavailableError


class EnvironmentHealthTest(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location("environment_health_entrypoint", Path(__file__).resolve().parent.parent / "main.py")
        self.entrypoint = importlib.util.module_from_spec(spec)
        with patch("pymongo.MongoClient"), patch("redis.Redis.from_url"), patch("file_store.FileStore"):
            spec.loader.exec_module(self.entrypoint)
        self.entrypoint.redis_client = Mock()
        self.entrypoint.kernel_redis_client = Mock()

    def test_ready_when_storage_and_workspace_are_available(self):
        self.assertEqual(self.entrypoint.health(), {"status": "ok"})
        self.entrypoint.mongo_client.admin.command.assert_called_once_with("ping")
        self.entrypoint.kernel_redis_client.hget.assert_not_called()

    def test_unavailable_when_public_or_kernel_redis_is_offline(self):
        for client in [self.entrypoint.redis_client, self.entrypoint.kernel_redis_client]:
            with self.subTest(client=client):
                client.ping.side_effect = ConnectionError("offline")
                self.assertEqual(self.entrypoint.health().status_code, 503)
                client.ping.side_effect = None

    def test_unavailable_when_mongodb_is_offline(self):
        self.entrypoint.mongo_client.admin.command.side_effect = ServerSelectionTimeoutError("offline")
        self.assertEqual(self.entrypoint.health().status_code, 503)

    def test_unavailable_when_workspace_initialization_failed(self):
        with patch.object(type(self.entrypoint.file_store), "revision", new_callable=PropertyMock, create=True) as revision:
            revision.side_effect = FileStoreUnavailableError("offline")
            self.assertEqual(self.entrypoint.health().status_code, 503)


if __name__ == "__main__":
    unittest.main()
