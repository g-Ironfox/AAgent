import os
from dataclasses import dataclass


def env(name: str, fallback: str) -> str:
    return os.getenv(name) or fallback


@dataclass(frozen=True)
class Settings:
    redis_url: str = ""
    mongo_host: str = "mongodb"
    mongo_port: int = 27017
    mongo_user: str | None = None
    mongo_password: str | None = None
    mongo_database: str = "agent"
    mongo_task_log_collection: str = "tool_task_logs"
    task_ttl_seconds: int = 86400
    max_wait_ms: int = 30000
    dispatch_timeout_seconds: float = 5.0
    callback_event_types: tuple[str, ...] = ("async_result",)

    @classmethod
    def from_env(cls) -> "Settings":
        redis_url = os.getenv("REDIS_URL")
        if not redis_url:
            host = env("REDIS_HOST", "redis")
            port = env("REDIS_PORT", "6379")
            database = env("REDIS_DB", "0")
            password = os.getenv("REDIS_PASSWORD")
            credentials = f":{password}@" if password else ""
            redis_url = f"redis://{credentials}{host}:{port}/{database}"
        event_types = tuple(
            event_type.strip()
            for event_type in env("TOOL_CALLBACK_EVENT_TYPES", "async_result").split(",")
            if event_type.strip()
        )
        return cls(
            redis_url=redis_url,
            mongo_host=env("MONGO_HOST", "mongodb"),
            mongo_port=int(env("MONGO_PORT", "27017")),
            mongo_user=os.getenv("MONGO_USER"),
            mongo_password=os.getenv("MONGO_PASS"),
            mongo_database=env("MONGO_DATABASE", "agent"),
            mongo_task_log_collection=env("MONGO_TOOL_TASK_LOG_COLLECTION", "tool_task_logs"),
            task_ttl_seconds=int(env("TOOL_TASK_TTL_SECONDS", "86400")),
            max_wait_ms=int(env("TOOL_MAX_WAIT_MS", "30000")),
            dispatch_timeout_seconds=float(env("TOOL_DISPATCH_TIMEOUT_SECONDS", "5")),
            callback_event_types=event_types,
        )