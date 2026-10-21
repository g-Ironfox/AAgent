"""Workflow-local Struct type definitions and recursive value validation."""
from __future__ import annotations

import copy
import re
from typing import Any

from workflow_contract import DATA_CONNECTION_TYPES

STRUCT_ID = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")


class StructValidationError(ValueError):
    pass


def validate_struct_definitions(value: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(value, list):
        raise StructValidationError("metadata.structs must be a list")
    result: dict[str, dict[str, Any]] = {}
    names: set[str] = set()
    for i, item in enumerate(value):
        path = f"metadata.structs[{i}]"
        if not isinstance(item, dict) or set(item) != {"id", "name", "color", "fields"}:
            raise StructValidationError(f"{path} must contain id, name, color, and fields")
        sid, name, color, fields = (item[k] for k in ("id", "name", "color", "fields"))
        if not isinstance(sid, str) or not STRUCT_ID.fullmatch(sid) or sid in result:
            raise StructValidationError(f"{path}.id is invalid or duplicated")
        if not isinstance(name, str) or not name.strip() or name.casefold() in names:
            raise StructValidationError(f"{path}.name must be non-empty and unique")
        if not isinstance(color, str) or not COLOR.fullmatch(color):
            raise StructValidationError(f"{path}.color must use #RRGGBB")
        if not isinstance(fields, list):
            raise StructValidationError(f"{path}.fields must be a list")
        seen: set[str] = set()
        clean_fields = []
        for j, field in enumerate(fields):
            fp = f"{path}.fields[{j}]"
            if not isinstance(field, dict) or set(field) != {"name", "type", "required"}:
                raise StructValidationError(f"{fp} must contain name, type, and required")
            fn, ft, req = (field[k] for k in ("name", "type", "required"))
            if not isinstance(fn, str) or not STRUCT_ID.fullmatch(fn) or fn in seen:
                raise StructValidationError(f"{fp}.name is invalid or duplicated")
            if not isinstance(ft, str) or not isinstance(req, bool):
                raise StructValidationError(f"{fp} has invalid type or required value")
            if ft not in DATA_CONNECTION_TYPES and not ft.startswith(("struct:", "list-struct:")):
                raise StructValidationError(f"{fp}.type is unsupported: {ft}")
            seen.add(fn)
            clean_fields.append({"name": fn, "type": ft, "required": req})
        names.add(name.casefold())
        result[sid] = {"id": sid, "name": name, "color": color, "fields": clean_fields}
    for sid, definition in result.items():
        for field in definition["fields"]:
            for ref in _refs(field["type"]):
                if ref not in result:
                    raise StructValidationError(f"Struct {sid} references unknown Struct: {ref}")
    _acyclic(result)
    return result


def _refs(value_type: str) -> list[str]:
    if value_type.startswith("struct:"):
        return [value_type[7:]]
    if value_type.startswith("list-struct:"):
        return [value_type[12:]]
    return []


def is_internal_type(value_type: Any, definitions: dict[str, Any]) -> bool:
    return value_type in DATA_CONNECTION_TYPES or (
        isinstance(value_type, str) and any(value_type in (f"struct:{sid}", f"list-struct:{sid}") for sid in definitions)
    )


def validate_value(value_type: str, value: Any, definitions: dict[str, Any], path: str = "$", *, copy_value: bool = False) -> Any:
    if value is None:
        raise StructValidationError(f"{path}: null is not supported")
    if value_type in DATA_CONNECTION_TYPES:
        if not _builtin(value_type, value):
            raise StructValidationError(f"{path}: expected {value_type}, got {_actual(value)}")
        return copy.deepcopy(value) if copy_value else value
    if value_type.startswith("list-struct:"):
        if not isinstance(value, list):
            raise StructValidationError(f"{path}: expected {value_type}, got {_actual(value)}")
        return [validate_value("struct:" + value_type[12:], v, definitions, f"{path}[{i}]", copy_value=copy_value) for i, v in enumerate(value)]
    if value_type.startswith("struct:"):
        sid = value_type[7:]
        definition = definitions.get(sid)
        if definition is None or not isinstance(value, dict):
            raise StructValidationError(f"{path}: expected {value_type}, got {_actual(value)}")
        fields = {field["name"]: field for field in definition["fields"]}
        extra = value.keys() - fields.keys()
        if extra:
            raise StructValidationError(f"{path}.{sorted(extra)[0]}: undeclared field")
        result = {}
        for name, field in fields.items():
            fp = f"{path}.{name}"
            if name not in value:
                if field["required"]:
                    raise StructValidationError(f"{fp}: required field is missing")
                continue
            result[name] = validate_value(field["type"], value[name], definitions, fp, copy_value=copy_value)
        return result
    raise StructValidationError(f"{path}: unsupported type {value_type}")


def _builtin(t: str, v: Any) -> bool:
    if t == "content": return isinstance(v, str)
    if t == "list-content": return isinstance(v, list) and all(isinstance(x, str) for x in v)
    if t == "message": return _message(v)
    if t == "list-message": return isinstance(v, list) and all(_message(x) for x in v)
    if t == "event": return isinstance(v, dict) and isinstance(v.get("event_type"), str) and bool(v["event_type"]) and "payload" in v
    if t == "list-event": return isinstance(v, list) and all(_builtin("event", x) for x in v)
    if t == "map-content": return isinstance(v, dict) and all(isinstance(k, str) and bool(k) and isinstance(x, str) for k, x in v.items())
    return False


def _message(v: Any) -> bool:
    return isinstance(v, dict) and set(v) == {"role", "content"} and v["role"] in {"system", "user", "assistant", "tool"} and isinstance(v["content"], str)


def _actual(v: Any) -> str:
    if isinstance(v, bool): return "boolean"
    if isinstance(v, (int, float)): return "number"
    if isinstance(v, dict): return "object"
    if isinstance(v, list): return "array"
    return type(v).__name__


def _acyclic(definitions: dict[str, dict[str, Any]]) -> None:
    visiting: set[str] = set()
    visited: set[str] = set()
    def visit(sid: str) -> None:
        if sid in visiting:
            raise StructValidationError(f"recursive Struct dependency: {sid}")
        if sid in visited: return
        visiting.add(sid)
        for field in definitions[sid]["fields"]:
            for ref in _refs(field["type"]): visit(ref)
        visiting.remove(sid)
        visited.add(sid)
    for sid in definitions: visit(sid)
