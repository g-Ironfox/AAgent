"""Build and validate tool definitions carried as workflow JSON content."""
from __future__ import annotations

import copy
import json
from typing import Any

from jsonschema import Draft202012Validator, SchemaError

TOOL_FIELDS = ("tool_name", "description", "schema", "required")
TOOL_DEFAULTS = {"tool_name": "", "description": "", "schema": {"type": "object", "properties": {}}}
TOOL_PORTS = {"tool_name": "name-in", "description": "description-in", "schema": "schema-in", "required": "required-in"}


def validate_parameters(schema: Any) -> None:
    if not isinstance(schema, dict) or schema.get("type") != "object":
        raise ValueError("schema must be a JSON Schema object with type 'object'")
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as error:
        raise ValueError(f"invalid parameter schema: {error.message}") from error
    required = schema.get("required", [])
    if any(name not in schema.get("properties", {}) for name in required):
        raise ValueError("required must reference names in schema.properties")


def validate_tool(tool: Any) -> dict[str, Any]:
    if not isinstance(tool, dict) or tool.get("type") != "function":
        raise ValueError("tool must be an object with type 'function'")
    function = tool.get("function")
    if not isinstance(function, dict):
        raise ValueError("tool.function must be an object")
    name = function.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("tool name must be a non-empty string")
    if "description" in function and not isinstance(function["description"], str):
        raise ValueError("tool description must be a string")
    validate_parameters(function.get("parameters"))
    return tool


def build_tool(name: Any, description: Any, schema: Any, required: Any = None) -> dict[str, Any]:
    if isinstance(schema, str):
        try:
            schema = json.loads(schema)
        except ValueError as error:
            raise ValueError("schema contains invalid JSON") from error
    parameters = copy.deepcopy(schema)
    if required is not None:
        if not isinstance(required, list) or any(not isinstance(item, str) or not item for item in required):
            raise ValueError("required must be a list of non-empty parameter names")
        if len(required) != len(set(required)):
            raise ValueError("required must not contain duplicate names")
        if not isinstance(parameters, dict):
            raise ValueError("schema must be a JSON Schema object")
        parameters["required"] = list(required)
    return validate_tool({"type": "function", "function": {
        "name": name, "description": description, "parameters": parameters,
    }})


def parse_tool_contents(contents: Any) -> list[dict[str, Any]]:
    if not isinstance(contents, list):
        raise ValueError("llm tools-in must be a list-content of Tool JSON strings")
    tools = []
    names = set()
    for index, content in enumerate(contents):
        try:
            if not isinstance(content, str):
                raise ValueError("Tool JSON must be a string")
            tool = validate_tool(json.loads(content))
            name = tool["function"]["name"]
            if name in names:
                raise ValueError(f"duplicate tool name: {name}")
            names.add(name)
            tools.append(tool)
        except (ValueError, TypeError) as error:
            raise ValueError(f"llm tools-in item {index + 1}: {error}") from error
    return tools


def validate_construct_tool_arguments(arguments: dict[str, Any]) -> None:
    for field in TOOL_FIELDS:
        if arguments.get(f"{field}_source", "fixed") not in ("fixed", "port"):
            raise ValueError(f"construct_tool {field}_source must be 'fixed' or 'port'")
    fixed = lambda field: arguments.get(f"{field}_source", "fixed") == "fixed"
    name = arguments.get("tool_name", "") if fixed("tool_name") else "dynamic_tool"
    description = arguments.get("description", "") if fixed("description") else ""
    schema = arguments.get("schema", TOOL_DEFAULTS["schema"]) if fixed("schema") else {"type": "object"}
    required = arguments.get("required") if fixed("required") else None
    if fixed("required") and "required" in arguments and required is None:
        raise ValueError("construct_tool required must be a list of parameter names")
    # When schema comes from a port, required names can only be checked at runtime.
    if not fixed("schema") and isinstance(required, list):
        schema = {"type": "object", "properties": {name: {} for name in required if isinstance(name, str)}}
    build_tool(name, description, schema, required)
