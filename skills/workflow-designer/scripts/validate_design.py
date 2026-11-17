"""Validate a workflow-design result and optionally export native .flow files.

This is local/offline validation. It neither deploys files nor verifies live
model registrations, credentials, process launch configuration, or Provider availability.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "agent"))
from workflow_validator import validate_workflow
from workflow_contract import data_ports_for_node

FORMAT = "aagent.workflow-design/1"
FILENAME = re.compile(r"[A-Za-z_][A-Za-z0-9_-]{0,114}\.flow")
MODEL_ID = re.compile(r"[0-9a-fA-F]{24}")
ROOT_FIELDS = {
    "schema_version", "name", "description", "metadata", "input_ports",
    "output_ports", "nodes", "connections", "workflow_nodes", "remote_tools",
}


class DesignError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise DesignError(message)


def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        require(key not in result, f"duplicate JSON key: {key}")
        result[key] = value
    return result


def read_json(path: Path) -> Any:
    def reject_constant(value: str) -> None:
        raise DesignError(f"invalid JSON constant: {value}")
    return json.loads(path.read_text(encoding="utf-8-sig"),
                      object_pairs_hook=unique_object,
                      parse_constant=reject_constant)


def check_execution_order(workflow: dict[str, Any]) -> None:
    """A data producer must precede the consumer on its control path.

    Native lifecycle validation handles branch/loop visibility. Remove only
    foreach/while_pop loop-in return edges, then check ancestry in the remaining tree.
    This also rejects data cycles and values read before first production.
    """
    nodes = {node["id"]: node for node in workflow["nodes"]}
    parents: dict[str, str] = {}
    for edge in workflow["connections"]:
        if edge["type"] != "control":
            continue
        if nodes[edge["toId"]]["type"] in {"foreach", "while_pop"} and edge["toPortId"] == "loop-in":
            continue
        require(edge["toId"] not in parents, "control merge is forbidden")
        parents[edge["toId"]] = edge["fromId"]
    for edge in workflow["connections"]:
        if edge["type"] == "control":
            continue
        current = parents.get(edge["toId"])
        seen = set()
        while current is not None and current not in seen and current != edge["fromId"]:
            seen.add(current)
            current = parents.get(current)
        require(current == edge["fromId"],
                f"{workflow['name']}: data source must execute before target: "
                f"{edge['fromId']}.{edge['fromPortId']} -> "
                f"{edge['toId']}.{edge['toPortId']}")


def check_required_data(workflow: dict[str, Any]) -> None:
    """Close native static-validation gaps for ordinary required value inputs.

    Tool parameter requiredness lives in the external tool schema, so it cannot
    be inferred from port snapshots. Their presence must be checked at deployment.
    """
    connected = {(e["toId"], e["toPortId"]) for e in workflow["connections"]
                 if e["type"] != "control"}
    structs = {s["id"]: s for s in workflow["metadata"].get("structs", [])}
    for node in workflow["nodes"]:
        kind = node["type"]
        args = node.get("arguments", {})
        inputs, _ = data_ports_for_node(node, workflow["input_ports"], workflow["output_ports"])
        required = set(inputs)
        if kind in {"input", "tool", "remote_async_tool"}:
            required = set()
        elif kind == "llm":
            required = {"messages-in"}
        elif kind == "construct_struct":
            required = {f["name"] for f in structs[args["struct_id"]]["fields"] if f["required"]}
        if kind == "router":
            require(all(branch["name"] != "$others" for branch in args["branches"]),
                    f"{workflow['name']}: router branch name $others collides with fallback")
        missing = sorted(p for p in required if (node["id"], p) not in connected)
        require(not missing,
                f"{workflow['name']}: required data inputs missing: node {node['id']}, ports {missing}")


def validate_design(result: Any) -> list[dict[str, Any]]:
    require(isinstance(result, dict), "design must be a JSON object")
    require(set(result) == {"format", "status", "entrypoint", "workflows", "errors"},
            "design has missing or unknown fields")
    require(result["format"] == FORMAT, f"format must be {FORMAT}")
    require(result["status"] in {"ready", "error"}, "status must be ready or error")
    require(isinstance(result["workflows"], list), "workflows must be an array")
    require(isinstance(result["errors"], list), "errors must be an array")
    if result["status"] == "error":
        require(result["entrypoint"] is None and not result["workflows"] and bool(result["errors"]),
                "error design requires null entrypoint, no workflows, and nonempty errors")
        for error in result["errors"]:
            require(isinstance(error, dict) and set(error) == {"code", "message"}
                    and all(isinstance(v, str) and bool(v.strip()) for v in error.values()),
                    "each error must contain nonempty code and message")
        return []

    require(not result["errors"], "ready design must have no errors")
    require(bool(result["workflows"]), "ready design must contain workflows")
    require(isinstance(result["entrypoint"], str), "entrypoint must be a filename")
    by_name: dict[str, dict[str, Any]] = {}
    folded_names: set[str] = set()
    for item in result["workflows"]:
        require(isinstance(item, dict) and set(item) == {"filename", "workflow"},
                "workflow entry must contain only filename and workflow")
        filename = item["filename"]
        require(isinstance(filename, str) and FILENAME.fullmatch(filename) is not None,
                f"unsafe or invalid filename: {filename!r}")
        require(filename.casefold() not in folded_names, f"duplicate filename: {filename}")
        folded_names.add(filename.casefold())
        workflow = item["workflow"]
        require(isinstance(workflow, dict) and set(workflow) == ROOT_FIELDS,
                f"{filename}: native workflow fields do not match this skill")
        require(workflow["name"] == filename, f"{filename}: name must equal filename")
        validate_workflow(workflow)
        require(workflow["remote_tools"] == [], f"{filename}: use metadata.tools")
        for node in workflow["nodes"]:
            require(isinstance(node.get("name"), str) and bool(node["name"].strip()),
                    f"{filename}: every node requires a nonempty display name: {node['id']}")
            require(type(node.get("x")) in (int, float) and math.isfinite(node["x"])
                    and type(node.get("y")) in (int, float) and math.isfinite(node["y"]),
                    f"{filename}: every node requires finite numeric x and y coordinates: {node['id']}")
            require(node["type"] not in {"local_tool", "remote_sync_tool"},
                    f"{filename}: forbidden generated node: {node['type']}")
            if node["type"] == "llm":
                model = node.get("arguments", {}).get("model")
                require(isinstance(model, str) and MODEL_ID.fullmatch(model) is not None,
                        f"{filename}: llm requires a real model registration ID")
        encoded = json.dumps(workflow, ensure_ascii=False, allow_nan=False)
        require(len(encoded.encode("utf-8")) <= 512 * 1024,
                f"{filename}: exceeds workflow API 512 KiB limit")
        check_required_data(workflow)
        check_execution_order(workflow)
        by_name[filename] = workflow
    require(result["entrypoint"] in by_name, "entrypoint is not included")

    dependencies: dict[str, list[str]] = {}
    for filename, workflow in by_name.items():
        declarations = workflow["workflow_nodes"]
        names = [ref["name"] for ref in declarations]
        require(len(names) == len(set(names)), f"{filename}: duplicate dependency declaration")
        calls = [node for node in workflow["nodes"] if node["type"] == "workflow"]
        call_names = {node["arguments"]["workflow_name"] for node in calls}
        require(set(names) == call_names, f"{filename}: declarations must match used dependencies")
        for name in names:
            require(name in by_name, f"{filename}: missing complete dependency {name}")
        for reference in [*declarations, *calls]:
            name = reference["arguments"]["workflow_name"] if reference.get("type") == "workflow" else reference["name"]
            for side in ("input_ports", "output_ports"):
                require(reference[side] == by_name[name][side],
                        f"{filename}: stale {side} snapshot for {name}")
        dependencies[filename] = names

    visiting: set[str] = set()
    visited: set[str] = set()
    ordered: list[dict[str, Any]] = []

    def visit(name: str) -> None:
        require(name not in visiting, f"recursive workflow dependency: {name}")
        if name in visited:
            return
        visiting.add(name)
        for child in dependencies[name]:
            visit(child)
        visiting.remove(name)
        visited.add(name)
        ordered.append({"filename": name, "workflow": by_name[name]})

    # Validate even unused workflows so hidden dependency cycles cannot slip in.
    for name in by_name:
        visit(name)
    reachable: set[str] = set()
    pending = [result["entrypoint"]]
    while pending:
        name = pending.pop()
        if name not in reachable:
            reachable.add(name)
            pending.extend(dependencies[name])
    require(reachable == set(by_name), "design includes workflows unused by the entrypoint")
    require([item["filename"] for item in result["workflows"]]
            == [item["filename"] for item in ordered],
            "workflows must be ordered with dependencies before their callers")
    return ordered


def export_design(items: list[dict[str, Any]], output_dir: Path) -> None:
    require(bool(items), "error results cannot be exported")
    # Exclusive creation avoids overwriting any user directory or existing file.
    # No runtime service is contacted; this only writes local native JSON files.
    output_dir.mkdir(parents=True, exist_ok=False)
    for item in items:
        target = output_dir / item["filename"]
        with target.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(item["workflow"], ensure_ascii=False, indent=2, allow_nan=False))
            stream.write("\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("design", type=Path, help="LLM result JSON")
    parser.add_argument("--output-dir", type=Path, help="new directory for native .flow files")
    args = parser.parse_args()
    try:
        result = read_json(args.design)
        items = validate_design(result)
        if args.output_dir is not None:
            export_design(items, args.output_dir)
        print(json.dumps({"valid": True, "status": result["status"],
                          "files": [item["filename"] for item in items],
                          "deployment_verified": False}, ensure_ascii=False))
        return 0
    except (ValueError, TypeError, KeyError, OSError, RecursionError) as error:
        print(json.dumps({"valid": False, "error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
