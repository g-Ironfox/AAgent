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
    queue: str
    event_type: str = Field(min_length=1, max_length=128)


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