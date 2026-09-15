import asyncio
import json
from datetime import datetime, timezone
from typing import Any

from redis.asyncio import Redis


TERMINAL_STATUSES = {"completed", "failed", "cancelled"}

TRANSITION_SCRIPT = """
local raw = redis.call('GET', KEYS[1])
if not raw then
  return {0, 'missing'}
end

local task = cjson.decode(raw)
if task.status == 'completed' or task.status == 'failed' or task.status == 'cancelled' then
  return {0, 'terminal'}
end

local expected = cjson.decode(ARGV[1])
local allowed = false
for _, status in ipairs(expected) do
  if task.status == status then
    allowed = true
    break
  end
end
if not allowed then
  return {0, 'conflict'}
end

local patch = cjson.decode(ARGV[2])
for key, value in pairs(patch) do
  task[key] = value
end
task.updated_at = ARGV[3]

local encoded = cjson.encode(task)
redis.call('SET', KEYS[1], encoded, 'EX', ARGV[4])
redis.call('LPUSH', KEYS[2], task.status)
redis.call('LTRIM', KEYS[2], 0, 0)
redis.call('EXPIRE', KEYS[2], ARGV[4])
if ARGV[5] ~= '' then
    redis.call('LPUSH', KEYS[3], ARGV[5])
end
return {1, encoded}
"""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class TaskStore:
    def __init__(self, redis: Redis, ttl_seconds: int = 86400):
        self.redis = redis
        self.ttl_seconds = ttl_seconds

    @staticmethod
    def task_key(task_id: str) -> str:
        return f"tool:task:{task_id}"

    @staticmethod
    def updates_key(task_id: str) -> str:
        return f"tool:task:{task_id}:updates"

    async def create(self, task: dict[str, Any]) -> bool:
        encoded = json.dumps(task, ensure_ascii=False, separators=(",", ":"))
        created = await self.redis.set(
            self.task_key(task["task_id"]),
            encoded,
            ex=self.ttl_seconds,
            nx=True,
        )
        if not created:
            return False
        created_at = datetime.fromisoformat(task["created_at"]).timestamp()
        await self.redis.zadd("tool:tasks:recent", {task["task_id"]: created_at})
        await self.redis.zremrangebyscore("tool:tasks:recent", "-inf", created_at - self.ttl_seconds)
        return True

    async def get(self, task_id: str) -> dict[str, Any] | None:
        raw = await self.redis.get(self.task_key(task_id))
        if raw is None:
            return None
        return json.loads(raw)

    async def list_recent(self, limit: int = 100) -> list[dict[str, Any]]:
        task_ids = await self.redis.zrevrange("tool:tasks:recent", 0, limit - 1)
        if not task_ids:
            return []
        values = await self.redis.mget([self.task_key(task_id) for task_id in task_ids])
        tasks = [json.loads(value) for value in values if value is not None]
        missing = [task_id for task_id, value in zip(task_ids, values) if value is None]
        if missing:
            await self.redis.zrem("tool:tasks:recent", *missing)
        return tasks

    async def transition(
        self,
        task_id: str,
        expected: set[str],
        patch: dict[str, Any],
        callback_event: dict[str, Any] | None = None,
    ) -> tuple[bool, str | dict[str, Any]]:
        result = await self.redis.eval(
            TRANSITION_SCRIPT,
            3,
            self.task_key(task_id),
            self.updates_key(task_id),
            "tool:callback:outbox",
            json.dumps(sorted(expected)),
            json.dumps(patch, ensure_ascii=False, separators=(",", ":")),
            utc_now(),
            self.ttl_seconds,
            (
                json.dumps(callback_event, ensure_ascii=False, separators=(",", ":"))
                if callback_event
                else ""
            ),
        )
        changed = bool(result[0])
        payload = result[1]
        return changed, json.loads(payload) if changed else payload

    async def wait_for_terminal(self, task_id: str, timeout_seconds: float) -> dict[str, Any] | None:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout_seconds

        while True:
            task = await self.get(task_id)
            if task is None or task["status"] in TERMINAL_STATUSES:
                return task

            remaining = deadline - loop.time()
            if remaining <= 0:
                return await self.get(task_id)
            await self.redis.blpop(self.updates_key(task_id), timeout=remaining)