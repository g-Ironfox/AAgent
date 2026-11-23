"""Workflow-local function declarations and metadata-derived node interfaces."""
from __future__ import annotations

import copy
from typing import Any

from workflow_contract import node_argument
from workflow_structs import STRUCT_ID, is_internal_type, validate_struct_definitions


def bind_function_interfaces(workflow: dict[str, Any]) -> dict[str, Any]:
    """Return an independent document with function ports resolved from metadata."""
    workflow = copy.deepcopy(workflow)
    definitions = validate_struct_definitions(workflow.get("metadata", {}).get("structs", []))
    functions = {}
    names = set()
    for function in workflow.get("metadata", {}).get("functions", []):
        fid, name = function["id"], function["name"]
        if not STRUCT_ID.fullmatch(fid) or fid in functions:
            raise ValueError(f"duplicate or invalid function id: {fid}")
        if not name.strip() or name.strip().casefold() in names:
            raise ValueError(f"duplicate or empty function name: {name}")
        for side in ("input_ports", "output_ports"):
            seen = set()
            for port in function[side]:
                if not port["name"].strip() or port["name"] in seen:
                    raise ValueError(f"function {fid} has duplicate or empty {side}")
                if not is_internal_type(port["type"], definitions):
                    raise ValueError(f"function {fid} has unknown port type: {port['type']}")
                seen.add(port["name"])
        functions[fid] = function
        names.add(name.strip().casefold())
    for node in workflow["nodes"]:
        kind = node["type"]
        if kind in {"function_input", "function_output"}:
            function_id = node.get("function_id")
            if function_id is None:
                raise ValueError(f"{kind} must belong to a function")
            if function_id not in functions:
                raise ValueError(f"node {node['id']} references unknown function: {function_id}")
            side = "input_ports" if kind == "function_input" else "output_ports"
            node["function_ports"] = copy.deepcopy(functions[function_id][side])
        elif kind == "function_call":
            target = node_argument(node, "function_id")
            if target not in functions:
                raise ValueError(f"function_call references unknown function: {target}")
            for side in ("input_ports", "output_ports"):
                if side in node and node[side] != functions[target][side]:
                    raise ValueError(f"function_call {node['id']} has stale {side}")
                node[side] = copy.deepcopy(functions[target][side])
        # Legacy body ownership is unnecessary: only boundaries identify a
        # function at runtime. Validation infers membership from control edges.
        if kind not in {"function_input", "function_output"}:
            node.pop("function_id", None)
    return workflow
