import unittest
from unittest.mock import AsyncMock, MagicMock

from task_log_repository import TaskLogRepository


class AsyncCursor:
    def __init__(self, documents):
        self._iterator = iter(documents)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self._iterator)
        except StopIteration as error:
            raise StopAsyncIteration from error


class TaskLogRepositoryQueryTests(unittest.IsolatedAsyncioTestCase):
    async def test_list_recent_returns_latest_task_snapshots(self):
        tasks = [
            {"task_id": "task-2", "status": "completed"},
            {"task_id": "task-1", "status": "working"},
        ]
        collection = MagicMock()
        collection.aggregate = AsyncMock(return_value=AsyncCursor(tasks))
        repository = TaskLogRepository(collection)

        result = await repository.list_recent(25)

        self.assertEqual(tasks, result)
        pipeline = collection.aggregate.await_args.args[0]
        self.assertEqual({"$sort": {"logged_at": -1}}, pipeline[0])
        self.assertEqual({"$limit": 25}, pipeline[-2])

    async def test_get_latest_returns_task_snapshot(self):
        task = {"task_id": "task-1", "status": "failed"}
        collection = MagicMock()
        collection.find_one = AsyncMock(return_value={"task": task})
        repository = TaskLogRepository(collection)

        result = await repository.get_latest("task-1")

        self.assertEqual(task, result)
        collection.find_one.assert_awaited_once_with(
            {"task_id": "task-1"},
            {"_id": 0, "task": 1},
            sort=[("logged_at", -1)],
        )

    async def test_get_latest_returns_none_for_missing_task(self):
        collection = MagicMock()
        collection.find_one = AsyncMock(return_value=None)
        repository = TaskLogRepository(collection)

        self.assertIsNone(await repository.get_latest("missing"))


if __name__ == "__main__":
    unittest.main()