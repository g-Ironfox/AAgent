"""Validation and comparison helpers for file and process permissions."""

from typing import Any

DEFAULT_PERMISSIONS = {
    "runtime": {"read": 0, "write": 0},
    "required": {"read": 0, "write": 0},
}


def normalize_permissions(value: Any = None) -> dict[str, dict[str, int]]:
    if value is None:
        value = DEFAULT_PERMISSIONS
    if not isinstance(value, dict) or set(value) != {"runtime", "required"}:
        raise ValueError("permissions must contain runtime and required levels")
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
