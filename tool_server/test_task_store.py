import json
import unittest
from unittest.mock import AsyncMock

from task_store import TaskStore


class FakeRedis:
    def __init__(self):
        self.created = True
        self.transition_result = [1, ""]

    async def set(self, *args, **kwargs):
        return self.created

    async def zadd(self, *args, **kwargs):
        return None

    async def zremrangebyscore(self, *args, **kwargs):
        return None

    async def eval(self, *args, **kwargs):
        return self.transition_result


class TaskStoreLogTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.redis = FakeRedis()
        self.task_logs = AsyncMock()
        self.store = TaskStore(self.redis, task_logs=self.task_logs)
        self.task = {
            "task_id": "task-1",
            "tool": "test.echo",
            "provider_id": None,
            "status": "pending",
            "created_at": "2026-09-18T00:00:00+00:00",
            "updated_at": "2026-09-18T00:00:00+00:00",
        }

    async def test_create_records_created_task(self):
        self.assertTrue(await self.store.create(self.task))

        self.task_logs.record.assert_awaited_once_with("created", self.task)

    async def test_duplicate_create_does_not_record_log(self):
        self.redis.created = False

        self.assertFalse(await self.store.create(self.task))
        self.task_logs.record.assert_not_awaited()

    async def test_successful_transition_records_updated_snapshot(self):
        updated = {**self.task, "status": "working"}
        self.redis.transition_result = [1, json.dumps(updated)]

        changed, result = await self.store.transition("task-1", {"pending"}, {"status": "working"})

        self.assertTrue(changed)
        self.assertEqual(updated, result)
        self.task_logs.record.assert_awaited_once_with("transition", updated)

    async def test_rejected_transition_does_not_record_log(self):
        self.redis.transition_result = [0, "conflict"]

        changed, result = await self.store.transition("task-1", {"pending"}, {"status": "working"})

        self.assertFalse(changed)
        self.assertEqual("conflict", result)
        self.task_logs.record.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()