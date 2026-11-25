"""Validate a proposed ALFWorld main revision without executing or writing it.

Used by the experimental iterator through a fixed, read-only workspace tool.
This is a syntax/capability gate, not evidence of improved task performance.
"""
from __future__ import annotations

import json
import re
from typing import Any

from workflow_parser import parse_workflow
from workflow_validator import validate_workflow


PURE_NODES = {
    "input", "output", "function_input", "function_output", "function_call", "router",
    "construct_message", "construct_content", "construct_map_content", "construct_struct",
    "struct_get", "struct_update", "struct_to_json", "json_to_struct", "map_content_get",
    "number_to_content", "deserialize_json", "construct_list", "list_append", "list_length",
    "list_get", "list_slice", "foreach", "while_pop", "context_create", "context_read",
    "context_write", "llm", "tool",
}


def _without_layout(node: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in node.items() if k not in {"x", "y", "name"}}


def _check_capabilities(current: dict[str, Any], candidate: dict[str, Any]) -> None:
    for side in ("input_ports", "output_ports"):
        if candidate[side] != current[side]:
            raise ValueError(f"main {side} must remain unchanged")
    old_tools = current.get("metadata", {}).get("tools", [])
    if candidate.get("metadata", {}).get("tools", []) != old_tools:
        raise ValueError("main tool declarations must remain unchanged")
    # The shipped main may only read its bound experience file. Freeze the tool
    # and its entire data dependency chain, not merely a model-supplied file ID.
    old_nodes = {n["id"]: n for n in current["nodes"]}
    new_nodes = {n["id"]: n for n in candidate["nodes"]}
    protected = {n["id"] for n in current["nodes"] if n["type"] == "tool"}
    if {n["id"] for n in candidate["nodes"] if n["type"] == "tool"} != protected:
        raise ValueError("main cannot add or remove workspace tool nodes")
    for node_id in protected:
        if old_nodes[node_id].get("arguments", {}).get("tool") != "workspace.get_file":
            raise ValueError("main baseline must contain read-only workspace.get_file tools only")
    pending = list(protected)
    while pending:
        target = pending.pop()
        for edge in current["connections"]:
            if edge["type"] != "control" and edge["toId"] == target and edge["fromId"] not in protected:
                protected.add(edge["fromId"])
                pending.append(edge["fromId"])
    for node_id in protected:
        if node_id not in new_nodes or _without_layout(old_nodes[node_id]) != _without_layout(new_nodes[node_id]):
            raise ValueError(f"bound experience reader must remain unchanged: {node_id}")
        old_edges = [e for e in current["connections"] if e["type"] != "control" and e["toId"] == node_id]
        new_edges = [e for e in candidate["connections"] if e["type"] != "control" and e["toId"] == node_id]
        normalize = lambda edges: sorted(json.dumps({k: v for k, v in e.items() if k != "id"}, sort_keys=True) for e in edges)
        if normalize(old_edges) != normalize(new_edges):
            raise ValueError(f"bound experience reader wiring must remain unchanged: {node_id}")
    models = {n.get("arguments", {}).get("model") for n in current["nodes"] if n["type"] == "llm"}
    if not models or any(not isinstance(m, str) or not m or m.startswith("REPLACE_WITH_") for m in models):
        raise ValueError("main baseline requires concrete model bindings")
    if not any(n["type"] == "llm" for n in candidate["nodes"]):
        raise ValueError("main must retain an LLM decision node")
    for node in candidate["nodes"]:
        if node["type"] not in PURE_NODES:
            raise ValueError(f"main cannot use capability node {node['type']}")
        if node["type"] == "llm":
            args = node.get("arguments", {})
            if args.get("model") not in models:
                raise ValueError("main model bindings must remain unchanged")
            if args.get("tool_calls") is not False or args.get("tools"):
                raise ValueError("main LLM tool calls must remain disabled")


def prepare_main_update(current: dict[str, Any], revision: int, proposal: str) -> dict[str, Any]:
    """Return a checked candidate plus a CAS revision; rejection never mutates state."""
    result = {"status": "rejected", "content": "", "error": "",
              "name": current["name"], "revision": current["revision"]}
    try:
        if isinstance(revision, bool) or revision != current["revision"]:
            raise ValueError("main revision conflict; discard stale proposal and read main again")
        if not current["name"].endswith("-main.flow") or current["name"].endswith("-stable-main.flow"):
            raise ValueError("only a task main workflow can be evolved; stable-main is immutable")
        if not isinstance(proposal, str) or len(proposal) > 1_000_000:
            raise ValueError("candidate must be JSON text of at most 1000000 characters")
        text = proposal.strip()
        fenced = re.fullmatch(r"```(?:json)?\s*\n(.*?)\n```", text, flags=re.DOTALL)
        if fenced:
            text = fenced.group(1)
        candidate = json.loads(text)
        if not isinstance(candidate, dict):
            raise ValueError("candidate must be a complete workflow JSON object")
        original = json.loads(current["content"])
        validate_workflow(candidate)
        _check_capabilities(original, candidate)
        parse_workflow(candidate)
        # Layout-only edits do not create new executable revisions.
        comparable = lambda doc: {**doc, "nodes": [_without_layout(n) for n in doc["nodes"]]}
        result["status"] = "unchanged" if comparable(original) == comparable(candidate) else "ready"
        result["content"] = json.dumps(candidate, ensure_ascii=False, indent=2) + "\n"
    except (ValueError, TypeError, KeyError, RecursionError) as error:
        result["error"] = str(error)
    return result
