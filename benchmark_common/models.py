"""Validated, versioned benchmark configuration shared by both services."""
import json
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator


class JobConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    name: str = Field(default="ALFWorld evaluation", min_length=1, max_length=120)
    workflow_file_id: str = Field(min_length=1, max_length=200)
    split: Literal["train", "valid_seen", "valid_unseen"] = "valid_unseen"
    episodes: int = Field(default=1, ge=1, le=10000, strict=True)
    max_steps: int = Field(default=50, ge=1, le=1000, strict=True)
    seed: int = Field(default=42, ge=0, le=2147483647, strict=True)
    action_timeout: float = Field(default=180, ge=1, le=3600)
    startup_timeout: float = Field(default=60, ge=1, le=600)
    admissible_commands: bool = False
    inputs: dict = Field(default_factory=dict)

    @field_validator("name", "workflow_file_id")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("must not be blank")
        return value.strip()

    @field_validator("inputs")
    @classmethod
    def json_inputs(cls, value):
        if len(json.dumps(value, allow_nan=False).encode("utf-8")) > 65536:
            raise ValueError("inputs must be at most 64 KiB of JSON")
        # MongoDB cannot store arbitrary integer sizes.
        def validate(item):
            if isinstance(item, int) and not -(2**63) <= item < 2**63:
                raise ValueError("input integers must fit signed 64 bits")
            if isinstance(item, dict):
                for key, child in item.items():
                    if key.startswith("$") or "." in key or "\x00" in key:
                        raise ValueError("input keys cannot contain dots, NUL or start with $")
                    validate(child)
            elif isinstance(item, list):
                for child in item:
                    validate(child)
        validate(value)
        return value


def summarize(results, requested):
    return {"requested": requested, "completed": len(results),
            "successes": sum(bool(item.get("success")) for item in results),
            "errors": sum(item.get("status") == "error" for item in results),
            "success_rate": sum(bool(item.get("success")) for item in results) / len(results) if results else 0}
