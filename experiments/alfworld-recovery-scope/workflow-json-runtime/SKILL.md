---
name: workflow-json-runtime
description: Design and revise this experiment's AAgent Workflow 2.0 JSON using the current runtime declarations, validator, compiler, and execution semantics.
---

# Workflow JSON design from the current implementation

Use the accompanying generated node/schema reference as the language definition.
Its catalog comes from `agent_runtime/workflow_contract.py`; its schema, semantic checks,
compiler and execution excerpts come from the current `agent_runtime/` implementation.
This skill describes how to use that material. It does not replace the code.
Do not import node names or ports from an older workflow skill or from memory.

## Design against the code

1. Preserve the current workflow's root input/output contract and concrete model
   and file bindings unless the task explicitly authorizes changing them.
2. Look up each node in the generated catalog. Copy its exact authored fields,
   argument allowlist, dynamic ports and accepted data connection types. Node
   fragments need the metadata shown alongside them; they are not complete graphs.
3. Declare structs/functions in metadata before using their types or IDs. Use
   `bind_function_interfaces` as the source for function boundary and call ports.
   Keep graph edges inside their function region; call functions through
   `function_call` and return through `function_output`.
4. Wire control edges for execution and data edges for values. A data edge alone
   does not schedule its target. Use `control_ports_for_node` for special branches
   and `connection_validation_error` for endpoint/type compatibility. Connect a
   router's `branch$others`. A control output has at most one successor.
5. Check the whole graph with `validate_workflow`, then compile it with
   `parse_workflow`. Per-node JSON Schema validation alone does not check graph
   lifecycles, function regions, loop bodies, required inputs or tool bindings.

Ordinary control ports are `control-in`/`control-out`, except where the catalog
says otherwise. Root boundary nodes require matching `workflowPorts`. Functions
use metadata-derived interfaces. Do not copy compiled `successors`, `data_inputs`,
`_struct_definitions`, scheduler state or function frames into authored JSON.

A loop has `control-in`, `loop-out`, `loop-in`, `control-out`. Wire the final body
node back to `loop-in` and the post-loop successor from `control-out`. The actual
`_validate_branches_in_foreach` check forbids multiple outgoing control edges and
external entries in a loop body. Put branching inside a called local function
when needed; do not wire the function's internal branches into the caller loop.

## Runtime values and terminal I/O

Use the runtime's declared types. `content` is text; JSON objects in a content
port are JSON text. `number` excludes booleans. Struct/list-struct types require
metadata and runtime field validation. Root/tool interfaces have their own
boundary restrictions; verify them in the validator instead of assuming every
internal type is accepted there.

`deserialize_json` requires a JSON object and each requested key. A `content`
output preserves an existing string and serializes a non-string JSON value;
it does not create an arbitrary object-typed wire. For typed structs use
`json_to_struct`, `struct_get` and `struct_to_json`. Serialize plain text once.
Never strip backslashes globally or recursively parse model text that resembles
JSON. Preserve booleans/null and nested objects at persistence boundaries.

The current terminal reader is `read_terminal_queue`, with `list-out`. Its
implementation reads queued input and returns a terminal-message wait when the
queue is empty. Do not design the older wait-then-read-history pattern. Terminal
and subprocess nodes in the general catalog are unavailable to main evolution
when the evolution policy excludes them.

## Experimental main evolution and installed capabilities

For this iterator, `agent_runtime/workflow_evolution.py` is an additional capability gate.
Preserve root ports, model IDs, tool declarations, and the full data dependency
chain of existing `workspace.get_file` readers. The catalog's `main_policy` marks
which runtime types this gate permits; existence in the catalog grants no access.
The design LLM returns a complete main JSON document with tools disabled. Choose
an unchanged document when there is no evidence for a useful structural change.

`metadata.tools` declares expected interfaces; it does not register Python
handlers. The deployed tool registry must contain `workspace.prepare_main_update`
before main evolution can run. Source code containing that function does not mean
an already running scheduler has loaded it. A missing tool is an infrastructure
failure, not evidence that a candidate was rejected or that no learning was needed.

Workspace write access compares process `runtime.write >= file.required.write`.
Uploading flow content, applying ACL, and loading runtime tools are separate
operations. Flow JSON does not carry the workspace file ACL. In this experiment,
commit the experience summary before attempting main evolution, so an evolution
exception does not discard the independently saved experience. Accepted main
writes still need validation, a checkpoint and revision-checked update.

## Complete examples checked by the actual validator and compiler

Echo a content input without model or tool dependencies:

```json
{
  "schema_version": "2.0",
  "metadata": {"structs": [], "tools": [], "functions": []},
  "input_ports": [{"name": "value", "type": "content"}],
  "output_ports": [{"name": "value", "type": "content"}],
  "nodes": [
    {"id": "in", "type": "input", "arguments": {}, "workflowPorts": [{"id": "workflow:value", "name": "value", "type": "content"}]},
    {"id": "out", "type": "output", "arguments": {}, "workflowPorts": [{"id": "workflow:value", "name": "value", "type": "content"}]}
  ],
  "connections": [
    {"fromId": "in", "fromPortId": "control-out", "toId": "out", "toPortId": "control-in", "type": "control"},
    {"fromId": "in", "fromPortId": "workflow:value", "toId": "out", "toPortId": "workflow:value", "type": "content"}
  ]
}
```

Extract an `observation` value from an object encoded as JSON text. A nested
observation object becomes JSON text on `value`, not a new object wire type:

```json
{
  "schema_version": "2.0",
  "metadata": {"structs": [], "tools": [], "functions": []},
  "input_ports": [{"name": "record", "type": "content"}],
  "output_ports": [{"name": "value", "type": "content"}],
  "nodes": [
    {"id": "in", "type": "input", "arguments": {}, "workflowPorts": [{"id": "workflow:record", "name": "record", "type": "content"}]},
    {"id": "extract", "type": "deserialize_json", "arguments": {"outputs": [{"key": "observation", "type": "content"}]}},
    {"id": "out", "type": "output", "arguments": {}, "workflowPorts": [{"id": "workflow:value", "name": "value", "type": "content"}]}
  ],
  "connections": [
    {"fromId": "in", "fromPortId": "control-out", "toId": "extract", "toPortId": "control-in", "type": "control"},
    {"fromId": "extract", "fromPortId": "control-out", "toId": "out", "toPortId": "control-in", "type": "control"},
    {"fromId": "in", "fromPortId": "workflow:record", "toId": "extract", "toPortId": "content-in", "type": "content"},
    {"fromId": "extract", "fromPortId": "observation", "toId": "out", "toPortId": "workflow:value", "type": "content"}
  ]
}
```

Report validation, adoption, runtime success and improved task results separately.
Compilation does not establish provider availability or better ALFWorld behavior.
