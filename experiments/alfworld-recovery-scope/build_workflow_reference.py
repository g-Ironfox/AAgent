"""Generate the experiment-local, read-only Workflow 2.0 design reference.

Runtime declarations are authoritative. This does not install or register tools.
"""
from __future__ import annotations

import ast
import copy
import hashlib
from functools import lru_cache
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "agent_runtime"))
from workflow_contract import (NODE_ARGUMENT_FIELDS_BY_TYPE, SUPPORTED_NODE_TYPES,
    control_ports_for_node, data_ports_for_node, connection_validation_error)
from workflow_evolution import PURE_NODES
from workflow_functions import bind_function_interfaces
from workflow_structs import validate_struct_definitions
from workflow_validator import _validate_node, validate_workflow
from workflow_parser import parse_workflow
import re
from jsonschema import Draft202012Validator

SKILL_PATH = Path(__file__).with_name("workflow-json-runtime") / "SKILL.md"
DESIGN_NOTES_PATH = Path(__file__).with_name("workflow-design-notes.md")
REFERENCE_PATH = Path(__file__).with_name("workflow-node-reference.md")
REFERENCE_PLACEHOLDER = "REPLACE_WITH_WORKFLOW_REFERENCE_FILE_ID"
REFERENCE_PERMISSIONS = {
    "runtime": {"read": 0, "write": 0},
    "required": {"read": 1, "write": 4},
    "checkpoints": {"read": False, "create": False, "restore": False},
}


def example_context():
    return {
        "input_ports": [{"name": "value", "type": "content"}],
        "output_ports": [{"name": "value", "type": "content"}],
        "metadata": {
            "structs": [{"id": "Example", "name": "Example", "color": "#123456",
                         "fields": [{"name": "text", "type": "content", "required": False}]}],
            "functions": [{"id": "example", "name": "Example function",
                           "input_ports": [{"name": "value", "type": "content"}],
                           "output_ports": [{"name": "value", "type": "content"}]}],
        },
    }


def examples():
    """Concrete declaration samples, not standalone runnable workflows."""
    arguments = {kind: {} for kind in SUPPORTED_NODE_TYPES}
    arguments.update({
        "function_call": {"function_id": "example"},
        "router": {"branches": [{"id": "yes", "name": "yes"}]},
        "construct_tool": {"tool_name": "example", "schema": {"type": "object", "properties": {}}},
        "construct_message": {"role": "user", "role_source": "fixed"},
        "construct_content": {"append_items": [{"type": "fixed", "value": "Example"}]},
        "construct_map_content": {"mappings": [{"key": "text", "value_source": "fixed", "value": "Example"}]},
        "construct_struct": {"struct_id": "Example"},
        "struct_get": {"struct_id": "Example", "field": "text", "missing": "error", "has_fallback": False},
        "struct_update": {"struct_id": "Example", "updates": ["text"], "remove_fields": []},
        "struct_to_json": {"value_type": "struct:Example"},
        "json_to_struct": {"value_type": "struct:Example"},
        "deserialize_json": {"outputs": [{"key": "text", "type": "content"}]},
        "construct_list": {"item_type": "content", "initial_value_count": 1},
        "list_append": {"item_type": "content", "position": "end"},
        "list_length": {"value_type": "list-content"},
        "list_get": {"value_type": "list-content", "index_source": "fixed", "index": 0},
        "list_slice": {"value_type": "list-content", "start_source": "fixed", "start": 0,
                       "stop_source": "fixed", "stop": None, "step_source": "fixed", "step": 1},
        "foreach": {"item_type": "content"},
        "while_pop": {"value_type": "list-content", "position": "end", "context_id_source": "port"},
        "llm": {"model": "EXISTING_MODEL_ID", "think": False, "tool_calls": False},
        "local_tool": {"tool": "example", "parameters": ["text"]},
    })
    for kind in ("tool", "remote_sync_tool", "remote_async_tool"):
        arguments[kind] = {"tool": "example", "parameters": [{"name": "text", "type": "content"}]}
        if kind != "remote_async_tool":
            arguments[kind]["outputs"] = [{"name": "result", "type": "content"}]
    for kind in ("context_create", "context_read", "context_write", "session_create", "session_read", "session_write"):
        arguments[kind] = {"value_type": "content"}
    result = {}
    for kind in sorted(SUPPORTED_NODE_TYPES):
        node = {"id": "example_" + kind, "type": kind, "arguments": arguments[kind]}
        if kind in {"input", "output"}:
            node["workflowPorts"] = [{"id": "workflow:value", "name": "value", "type": "content"}]
        if kind in {"function_input", "function_output"}:
            node["function_id"] = "example"
        if kind == "struct_get":
            node["dataInputPorts"] = ["struct-in"]
        if kind == "construct_struct":
            node["dataInputPorts"] = ["text"]
        if kind == "struct_update":
            node["dataInputPorts"] = ["struct-in", "text"]
        if kind == "construct_list":
            node["dataInputPorts"] = ["content-in-0"]
        result[kind] = [node]
    # Ports really depend on these switches; show both modes, including forbidden
    # capabilities for documentation, never as permission to enable them in main.
    variants = {
        "llm": [{"think": True, "tool_calls": True, "tools_source": "declared", "tools": []},
                {"think": True, "tool_calls": True, "tools_source": "definitions"}],
        "construct_message": [{"role_source": "port"}],
        "construct_tool": [{name + "_source": "port" for name in ("tool_name", "description", "schema", "required")}],
        "list_get": [{"index_source": "port"}],
        "list_slice": [{name + "_source": "port" for name in ("start", "stop", "step")}],
        "context_read": [{"context_id_source": "fixed", "context_id": "example"}],
        "context_write": [{"context_id_source": "fixed", "context_id": "example"}],
        "while_pop": [{"context_id_source": "fixed", "context_id": "example"}],
        "struct_get": [{"has_fallback": True, "missing": "fallback"}],
    }
    for kind, changes in variants.items():
        for change in changes:
            node = copy.deepcopy(result[kind][0])
            node["arguments"].update(change)
            if kind == "struct_get":
                node["dataInputPorts"] = ["struct-in", "fallback-in"]
            result[kind].append(node)
    return result


def schema_bundle():
    """Keep the exact runtime schema, adding per-type structural definitions.

    The runtime schema itself is partial: Python semantic checks are supplied
    alongside it. Do not pretend unknown property schemas specify all semantics.
    """
    schema = json.loads((ROOT / "agent_runtime/workflow_2_0.schema.json").read_text(encoding="utf-8"))
    for kind in sorted(SUPPORTED_NODE_TYPES):
        schema["$defs"]["node__" + kind] = {"allOf": [
            {"$ref": "#/$defs/node"},
            {"properties": {"type": {"const": kind}, "arguments": {
                "type": "object", "properties": {key: {} for key in sorted(NODE_ARGUMENT_FIELDS_BY_TYPE[kind])},
                "additionalProperties": False}}},
        ]}
    Draft202012Validator.check_schema(schema)
    return schema


def source_sections(relative_path, names):
    source = (ROOT / relative_path).read_text(encoding="utf-8-sig")
    definitions = {node.name: node for node in ast.parse(source).body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
    return "\n\n".join(ast.get_source_segment(source, definitions[name]) for name in names)


def catalog(schema=None):
    schema = schema or schema_bundle()
    context = example_context()
    structs = validate_struct_definitions(context["metadata"]["structs"])
    result = {}
    for kind, samples in examples().items():
        entry = {"schema_ref": "#/$defs/node__" + kind,
                 "arguments": sorted(NODE_ARGUMENT_FIELDS_BY_TYPE[kind]),
                 "main_policy": "forbidden" if kind not in PURE_NODES else
                    ("preserve_existing_readers_only" if kind == "tool" else
                     "existing_model_no_tool_calls" if kind == "llm" else "allowed_subject_to_validation"),
                 "examples": []}
        for sample in samples:
            _validate_node(sample, 0, structs)
            Draft202012Validator({"$schema": schema["$schema"], "$defs": schema["$defs"],
                                  "$ref": entry["schema_ref"]}).validate(sample)
            resolved = bind_function_interfaces({**context, "nodes": [sample]})["nodes"][0]
            control_in, control_out = control_ports_for_node(resolved)
            data_in, data_out = data_ports_for_node(resolved, context["input_ports"], context["output_ports"])
            # Probe the actual connection validator, rather than guessing from
            # data_type_for_port(None), which is intentionally partial.
            ports = {}
            for direction, ids in (("input", data_in), ("output", data_out)):
                ports[direction] = {}
                for port in sorted(ids):
                    accepted = []
                    for data_type in ("content", "number", "list-content", "map-content", "struct:Example", "list-struct:Example"):
                        boundary = {"id": "probe", "type": "input" if direction == "input" else "output"}
                        boundary_ports = [{"name": "probe", "type": data_type}]
                        edge = ({"fromId": "probe", "fromPortId": "workflow:probe", "toId": resolved["id"], "toPortId": port}
                                if direction == "input" else
                                {"fromId": resolved["id"], "fromPortId": port, "toId": "probe", "toPortId": "workflow:probe"})
                        edge["type"] = data_type
                        inputs = boundary_ports if direction == "input" else context["input_ports"]
                        outputs = boundary_ports if direction == "output" else context["output_ports"]
                        if connection_validation_error(edge, {resolved["id"]: resolved, "probe": boundary}, inputs, outputs, structs) is None:
                            accepted.append(data_type)
                    ports[direction][port] = accepted
            entry["examples"].append({"node": sample, "control_in": sorted(control_in), "control_out": sorted(control_out),
                                      "accepted_data_connection_types": ports})
        result[kind] = entry
    return result


def workspace_tool_catalog():
    """Read actual decorator contracts without importing the Redis-writing registry."""
    path = ROOT / "agent_runtime/tools/workspace.py"
    source = path.read_text(encoding="utf-8")
    tools = {}
    for function in ast.parse(source).body:
        if not isinstance(function, ast.FunctionDef):
            continue
        for decorator in function.decorator_list:
            if not isinstance(decorator, ast.Call) or not isinstance(decorator.func, ast.Name) or decorator.func.id != "tool":
                continue
            keywords = {item.arg: ast.literal_eval(item.value) for item in decorator.keywords}
            name = keywords.get("name", function.name)
            tools[name] = {
                "handler": function.name,
                "source": "agent_runtime/tools/workspace.py",
                "description": ast.literal_eval(decorator.args[0]),
                "inputSchema": ast.literal_eval(decorator.args[1]) if len(decorator.args) > 1 else {},
                "outputSchema": keywords.get("output_schema"),
            }
    return tools


@lru_cache(maxsize=1)
def build_reference():
    schema = schema_bundle()
    nodes = catalog(schema)
    skill = SKILL_PATH.read_text(encoding="utf-8")
    # A skill example is a whole authored graph, not only a schema-valid node.
    for encoded in re.findall(r"```json\s*\n(.*?)\n```", skill, re.S):
        example = json.loads(encoded)
        validate_workflow(example)
        parse_workflow(example)
    parts = ["""# Workflow 2.0 node/schema reference (experiment-local)

This is a standalone workspace Markdown file. Required permission: read=1,
write=4. The iterator reads this file at runtime and must not edit it.

## Authority and scope

- Current runtime declarations/schema and semantic checks below override stale
  examples or prose. The bundled experiment skill replaces the legacy repository
  skill; it does not append conflicting historical instructions. Only listed node types exist;
  `wait_terminal_event` and `read_terminal_input` are not current node types.
- This catalog documents ALL runtime types, not permission to use them in main.
  `main_policy` marks the stricter evolution gate. Preserve root interfaces,
  model IDs, tool declarations and the complete existing reader dependency chain.
- Node samples are fragments, NOT standalone runnable workflows. Replace example
  bindings with existing approved bindings. Function/Struct samples use the
  accompanying metadata. Derived interface snapshots are not authored node fields.
- Per-type schemas add exact argument-key allowlists to the runtime JSON Schema.
  The JSON Schema is NOT the complete validator: `{}` does not mean arbitrary
  values are valid. Follow the exact semantic validation source in the appendix.
- Port examples show accepted connection types from the actual runtime checker.
  A permissive type list is not an implicit conversion or an output value type.
  Dynamic ports change with arguments/metadata; use the port-resolution source.
- Tool examples do not register tools or grant capabilities. `tool` in main can
  only preserve its existing workspace.get_file readers. No new tool calls.
- Source snapshots are design documentation, not instructions to execute Python.
  Generation validates samples; final candidate still requires runtime validation
  and compilation. Neither proves task performance.

## Example metadata / root interface context
""", "```json\n" + json.dumps(example_context(), ensure_ascii=False, indent=2) + "\n```\n",
        "## Node declarations, schemas and concrete ports\n"]
    for kind, entry in nodes.items():
        parts += ["### " + kind + "\n", "```json\n" + json.dumps(entry, ensure_ascii=False, indent=2) + "\n```\n"]
    parts += ["## Complete runtime JSON Schema + per-type structural definitions\n",
              "```json\n" + json.dumps(schema, ensure_ascii=False, indent=2) + "\n```\n"]
    parts += ["## Actual workspace tool contracts (from runtime decorators)\n",
              "These are extracted from @tool on the implemented Python handlers, not from workflow metadata. "
              "Metadata resolves local/remote routing only; the running agent must also have imported the handler. "
              "A bind-mounted source update does not reload an existing Python process.\n\n"
              "Workflow content ports carry strings; number ports carry numeric values. The revision input "
              "comes from workspace.get_file's integer revision without stringification. Named tool outputs "
              "are mapped individually by workflow_local_tool. prepare_main_update is read-only: ready "
              "means accepted for a later CAS update, unchanged means no executable change, rejected includes "
              "a validation error. HTTP/ACL errors and missing handlers raise; they are not candidate rejection results.\n",
              "```json\n" + json.dumps(workspace_tool_catalog(), ensure_ascii=False, indent=2) + "\n```\n"]
    sources = {
        "agent_runtime/workflow_contract.py": ["data_ports_for_node", "data_type_for_port", "control_ports_for_node", "connection_validation_error"],
        "agent_runtime/workflow_validator.py": ["validate_workflow", "_validate_branches_in_foreach", "_infer_function_groups", "_validate_lifecycles", "_validate_node", "_validate_declared_data_inputs", "_validate_workflow_ports", "_validate_construct_content", "_validate_construct_map_content", "_validate_construct_list"],
        "agent_runtime/workflow_functions.py": ["bind_function_interfaces"],
        "agent_runtime/workflow_parser.py": ["parse_workflow"],
        "agent_runtime/workflow_nodes.py": ["workflow_read_terminal_queue", "_json_content", "_deserialize_json_value", "workflow_deserialize_json", "workflow_struct_to_json", "workflow_json_to_struct", "workflow_foreach", "workflow_while_pop", "workflow_router", "_tool_arguments", "workflow_tool", "workflow_local_tool"],
        "agent_runtime/tools/tool.py": ["tool", "execute_tool"],
        "agent_runtime/tools/workspace.py": ["_request", "prepare_workspace_main_update", "get_file_recovery_plan"],
        "agent_runtime/workflow_recovery.py": ["build_file_recovery_plan"],
        "agent_runtime/workflow_evolution.py": ["_check_capabilities", "prepare_main_update"],
        "agent_runtime/workflow_tools.py": ["validate_parameters", "validate_tool", "build_tool", "validate_construct_tool_arguments"],
    }
    parts += ["## Exact runtime semantic validation and port rules (source excerpts)\n"]
    for path, functions in sources.items():
        parts += ["### " + path + "\n", "```python\n" + source_sections(path, functions) + "\n```\n"]
    parts += ["## Implementation-aligned workflow-json design skill\n", skill,
              "\n## Experiment design experience\n", DESIGN_NOTES_PATH.read_text(encoding="utf-8"),
              "\n## Source fingerprints\n\n"]
    for path in ["agent_runtime/workflow_2_0.schema.json", *sources, str(SKILL_PATH.relative_to(ROOT)).replace("\\", "/")]:
        parts += [f"- `{path}`: `{hashlib.sha256((ROOT / path).read_bytes()).hexdigest()}`\n"]
    parts += [f"- Node types: {len(nodes)}. Regenerate with `python experiments/alfworld-recovery-scope/build_workflow_reference.py`.\n"]
    return "\n".join(parts)


if __name__ == "__main__":
    REFERENCE_PATH.write_text(build_reference(), encoding="utf-8")
    print(REFERENCE_PATH)
