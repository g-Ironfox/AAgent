"""Validation and comparison helpers for file and process permissions."""

from typing import Any

DEFAULT_CHECKPOINT_PERMISSIONS = {"read": False, "create": False, "restore": False}
DEFAULT_PERMISSIONS = {
    "runtime": {"read": 0, "write": 0},
    "required": {"read": 0, "write": 0},
    "checkpoints": dict(DEFAULT_CHECKPOINT_PERMISSIONS),
}


def normalize_checkpoint_permissions(value: Any = None) -> dict[str, bool]:
    if value is None:
        return dict(DEFAULT_CHECKPOINT_PERMISSIONS)
    if not isinstance(value, dict) or set(value) - set(DEFAULT_CHECKPOINT_PERMISSIONS):
        raise ValueError("permissions.checkpoints must contain only read, create and restore flags")
    result = {**DEFAULT_CHECKPOINT_PERMISSIONS, **value}
    if any(type(flag) is not bool for flag in result.values()):
        raise ValueError("permissions.checkpoints flags must be booleans")
    return result


def normalize_permissions(value: Any = None) -> dict[str, Any]:
    if value is None:
        value = DEFAULT_PERMISSIONS
    if (not isinstance(value, dict) or not {"runtime", "required"} <= set(value)
            or set(value) - {"runtime", "required", "checkpoints"}):
        raise ValueError("permissions must contain runtime and required levels, with optional checkpoints flags")
    result = {}
    for group in ("runtime", "required"):
        levels = value[group]
        if not isinstance(levels, dict) or set(levels) != {"read", "write"}:
            raise ValueError(f"permissions.{group} must contain read and write levels")
        result[group] = {}
        for operation in ("read", "write"):
            level = levels[operation]
            if isinstance(level, bool) or not isinstance(level, int) or level < 0:
                raise ValueError(f"permissions.{group}.{operation} must be a non-negative integer")
            result[group][operation] = level
    result["checkpoints"] = normalize_checkpoint_permissions(value.get("checkpoints"))
    return result


def process_levels(process: dict[str, Any] | None) -> dict[str, int]:
    if process is None:
        return {"read": 0, "write": 0}
    permissions = process.get("permissions", {}).get("runtime", {})
    return {"read": permissions.get("read", 0), "write": permissions.get("write", 0)}


def can_access(process: dict[str, Any] | None, file: dict[str, Any], operation: str) -> bool:
    if process is None:
        return True
    permissions = normalize_permissions(file.get("permissions"))
    return process_levels(process)[operation] >= permissions["required"][operation]


def can_access_checkpoint(process: dict[str, Any] | None, operation: str) -> bool:
    if process is None:
        return True
    return process.get("permissions", {}).get("checkpoints", {}).get(operation) is True
