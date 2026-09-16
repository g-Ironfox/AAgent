import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ToolSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(pattern=r"^[A-Za-z0-9_-]+\.[A-Za-z0-9_.-]+$", max_length=128)
    description: str = Field(max_length=4096)
    inputSchema: dict[str, Any]
    outputSchema: dict[str, Any] | None = None
    annotations: dict[str, Any] = Field(default_factory=dict)


class RegisterMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["register"]
    provider_id: str = Field(min_length=1, max_length=128)
    revision: int = Field(ge=1)
    tools: list[ToolSchema] = Field(max_length=256)


class CallbackSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["redis"]
    queue: str = Field(min_length=1, max_length=256)
    event_type: str = Field(min_length=1, max_length=128)
    on: list[Literal["working", "completed", "failed"]] = Field(
        default_factory=lambda: ["working", "completed", "failed"],
        min_length=1,
        max_length=3,
    )
    context: dict[str, Any] = Field(default_factory=dict)

    @staticmethod
    def _validate_context(value: Any, depth: int = 0) -> None:
        if depth > 5:
            raise ValueError("callback context nesting is too deep")
        if isinstance(value, dict):
            if len(value) > 64:
                raise ValueError("callback context has too many fields")
            for key, nested in value.items():
                if not isinstance(key, str) or len(key) > 128:
                    raise ValueError("callback context field name is invalid")
                CallbackSpec._validate_context(nested, depth + 1)
        elif isinstance(value, list):
            if len(value) > 256:
                raise ValueError("callback context list is too large")
            for nested in value:
                CallbackSpec._validate_context(nested, depth + 1)

    def model_post_init(self, __context: Any) -> None:
        self._validate_context(self.context)
        try:
            encoded = json.dumps(self.context, ensure_ascii=False, separators=(",", ":"))
        except (TypeError, ValueError) as error:
            raise ValueError("callback context must be JSON serializable") from error
        if len(encoded.encode("utf-8")) > 16384:
            raise ValueError("callback context is too large")


class ToolCallRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    arguments: dict[str, Any]
    mode: Literal["wait", "async"] = "wait"
    timeout_ms: int = Field(default=30000, ge=1)
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=256)
    callback: CallbackSpec | None = None


class ProviderEvent(BaseModel):
    model_config = ConfigDict(extra="allow")

    type: Literal["accepted", "rejected", "status", "result", "pong", "ping"]
    task_id: str | None = None
    status: str | None = None
    progress: float | None = Field(default=None, ge=0, le=1)
    message: str | None = Field(default=None, max_length=4096)
    success: bool | None = None
    output: Any = None
    error: Any = None