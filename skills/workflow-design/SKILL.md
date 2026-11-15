---
name: workflow-design
description: Generate a complete Workflow 2.0 JSON workflow from a user request using only this skill and workflow read/write tools. Contains the serialization contract and complete built-in node catalog; no repository or node discovery is required.
---

# Workflow Design Skill

## Mission And Operating Model

The only design inputs are this skill and the user's request. The agent may have tools to read or write Workflow documents, but must assume it has no source-code access, node-catalog tool, schema tool, examples, or prior knowledge of the format. This skill is the complete design-time reference. Do not ask the user to provide node names or JSON examples.

The deliverable for a generation request is one complete, parseable Workflow 2.0 JSON object. Do not return a proposal, pseudo-JSON, partial patch, Markdown fence, or explanatory text instead of the object. Ask a concise clarification only when a missing environment-specific value makes a usable workflow impossible; never invent a model ID, registered tool, child workflow name, queue binding, or runtime capability. Otherwise make conservative assumptions and produce the JSON.

Read/write tools are only for document operations explicitly requested by the user. A design request that asks for JSON does not itself authorize persistence. A write may persist immediately: never probe with a guessed write. Use exact tool input shapes. If an existing workflow is to be changed, read that exact workflow first and preserve unrelated content unless replacement is requested.

## Hard Graph Rules

1. Each workflow's control graph is a DAG except for the single structured back-edge of each valid `foreach` body (`loop-in` to that same `foreach`). No other cycle is allowed, including self-loops, retry edges, Router back-edges, or arbitrary jumps. To request another round, publish an event through the workflow queue and let a new invocation process it; do not draw an event loop in one workflow.
2. A `foreach` body may contain no branch-capable node. Branch capability is based on semantics, not connected edge count. In particular, `router` and `json_tool` are forbidden in a foreach body even if only one outcome is connected. Keep the body a single-entry linear chain ending at the same foreach's `loop-in`. Put per-item conditional logic in a child workflow called as one parent step.
3. Branch outcomes must never reconverge within the same workflow. For each control outcome, compute the set of all downstream reachable nodes; those sets must be pairwise disjoint. A common node, child call, or Output is reconvergence, even several steps downstream. Give each outcome its own terminal Output.
4. To perform shared continuation after conditional work, move the branch and path-specific work into a child workflow. Give each child outcome its own Output; return through the child's call interface, then continue in the parent after the single workflow-call node. This is encapsulation, not a branch merge or join.
5. Events start a separate invocation; they do not synchronously call the next round. Specify continuation state, a stop condition, and a finite iteration/budget limit in the workflow's data contract. Do not claim exactly-once delivery, deduplication, delay, or recovery guarantees unless configured/documented.

## Workflow 2.0 JSON Contract

### Root object

Required keys: `schema_version`, `name`, `input_ports`, `output_ports`, `nodes`, `connections`. `schema_version` is exactly the string `2.0`. Allowed optional keys: `description`, `metadata`, `workflow_nodes`, `remote_tools` (legacy compatibility only). Do not add unknown root keys. For a portable normalized workflow, always include `description`, `metadata`, and `connections`, even when empty.

- `name`: 1-120 characters. `description`: string, at most 2000 characters.
- `input_ports`, `output_ports`: arrays (at most 50 each) of exact objects `{"name":"...","type":"..."}`. Names are 1-80 characters and unique case-insensitively after trimming within each array.
- `metadata`: object containing only optional `structs` and `tools`; omitted arrays mean `[]`. `metadata.tools` has at most 100 declarations.
- `workflow_nodes` and `remote_tools`, when used, are arrays of exact dependency snapshots: `{"name":"...","input_ports":[...],"output_ports":[...]}`. Prefer current `metadata.tools` for tool declarations; do not fabricate legacy dependencies.
- At most 200 nodes, 1000 connections, 50 workflow dependencies, 100 remote tool dependencies. Nodes must number 1-200. A Workflow has exactly one Input and at least one Output.

### Types and boundaries

Built-in data types are `content` (string), `message` (object with exactly `role` and `content`; role is `system|user|assistant|tool`, content string), `event` (Event object), `list-content`, `list-message`, `list-event` (arrays of corresponding values), and `map-content` (object of nonempty string keys to string values). Struct types are local to one workflow: `struct:<id>` and `list-struct:<id>`, where id matches `[A-Za-z_][A-Za-z0-9_]*`. Do not expose Struct types in workflow input/output or child/tool interface snapshots. Convert explicitly through JSON when crossing workflow boundaries.

`origin` is a reserved optional input name and must have type `event`. Input ports are available from the Input node as `workflow:<name>`. Output values are received through Output node inputs `workflow:<name>`.

### Node and edge shape

Each node has required nonempty unique `id` and supported `type`. Optional top-level fields are `name`, numeric `x`, numeric `y`, `arguments` (object), and type-specific shared fields: `workflowPorts`, `dataInputPorts`, `input_ports`, `output_ports`. No other fields are permitted. Put all configuration inside `arguments`; never put a parameter at node top level. Omit `arguments` or use `{}` when there are no parameters.

Input and Output nodes require `workflowPorts`, an exact snapshot of the matching root interface in order. Each item is `{"id":"workflow:<name>","name":"<name>","type":"<type>"}`. Callable `workflow` nodes require `input_ports` and `output_ports` exact snapshots of the target workflow interface. `dataInputPorts`, when required below, is an ordered list of every dynamic/declared data input ID, with no duplicates and no control ports.

Each connection is exactly `{"fromId":"node-id","fromPortId":"port-id","toId":"node-id","toPortId":"port-id","type":"..."}` with optional string `id`. `type` is `control` or an exact data type. Endpoints and ports must exist; data type must exactly match both endpoint port types. A control output has at most one successor; a control input may have multiple predecessors. Each data input has at most one source. Unconnected optional data inputs are allowed, but a required runtime value missing when read fails execution.

Input has `control-out`; Output has `control-in`; ordinary execution nodes have `control-in` and `control-out`. Router has `control-in`, one output for each branch id, and `branch$others` (no generic `control-out`). Foreach has `control-in`, `loop-out`, `loop-in`, and `control-out`. `json_tool` has `control-in`, success `control-out`, and optional failure `error-out`; an unhandled failure aborts execution. Required control connections must be wired: Input, ordinary node and Output ports; every Router outcome including fallback; all four Foreach ports. `json_tool.error-out` may remain unconnected only when the workflow intentionally lets tool errors fail the invocation.

## Built-In Node Catalog

Only use the following node `type` values. Except where noted, each listed node has ordinary `control-in` and `control-out`. Arguments not marked optional are required when shown. Do not invent additional arguments or ports.

| type | arguments (required; optional/default) | data input ports | data output ports |
|---|---|---|---|
| `input` | none | none | `workflow:<input name>` from root `input_ports` |
| `output` | none | `workflow:<output name>` from root `output_ports` | none |
| `router` | `branches: [{"id":"unique-port-id","name":"exact-match-value"}]` | `content-in: content` | none; branches are control outputs, plus fallback `branch$others` |
| `construct_message` | optional `role` (default `user`, enum system/user/assistant/tool), `role_source` (default `fixed`, fixed/port) | `content-in: content`; add `role-in: content` if role_source=`port` | `message-out: message` |
| `construct_content` | `append_items` | dynamic content ports described below | `content-out: content` |
| `construct_map_content` | `mappings` | dynamic content ports described below | `map-out: map-content` |
| `map_content_get` | none | `map-in: map-content`, `key-in: content` | `content-out: content` |
| `split_event` | none | `event-in: event` | `type-out: content`, `payload-out: content` (payload as JSON text) |
| `construct_event` | `event_type` nonblank string | `payload-in: content` (JSON object text) | `event-out: event` |
| `publish_event` | none | `event-in: event` | none; publishes to the workflow queue |
| `deserialize_json` | `outputs: [{"key":"object-key","type":"data-type"}]` | `content-in: content` (JSON object text) | one output port per key, typed as declared |
| `construct_list` | `item_type`, `initial_value_count` (integer 0-20) | `<item_type>-in-0` through `...-(count-1)` | `list-out: list-<item_type>` |
| `list_append` | `item_type`, `position` (`start` or `end`) | `list-in: list-<item_type>`, `item-in: <item_type>` | `list-out: list-<item_type>` |
| `foreach` | `item_type` | `list-in: list-<item_type>` | `item-out: <item_type>` |
| `history` | `event_types` (nonempty unique subset terminal/response), `limit` (integer 1-1000) | none | `events: list-event` |
| `llm` | optional `model`, `think` (boolean), `tool_calls` (boolean), `tools` (array) | `messages-in: list-message`; if tool_calls=true, optional `available-tools-in: list-content` | `output: content`; if think=true `reasoning: content`; if tool_calls=true `tool_calls: list-content` |
| `tool` | `tool`, `parameters: port[]`, `outputs: port[]`; optional `mode` (only sync), `timeout_ms` positive integer, `callback` (only null) | one typed input for each parameters item | one typed output for each outputs item |
| `json_tool` | none | `tool-name: content`, `arguments-json: content` | `result-json: content`, `error-json: content`; success uses `control-out`, optional handled failure uses `error-out` |
| `local_tool` (legacy) | `tool`; optional `parameters: string[]` | one `content` input per parameter name | `output: content` |
| `remote_sync_tool` (legacy) | `tool`; optional `parameters: port[]`, `outputs: port[]`, `timeout_ms` | one typed input per parameter | one typed output per output declaration |
| `remote_async_tool` | `tool`; optional `parameters: port[]`, `timeout_ms`, `callback` | one typed input per parameter | `task_id: content` |
| `context_create` | `value_type`; optional `context_id` | `initial-value: value_type` | `context-id: content` |
| `context_read` | `value_type`; optional `context_id_source` (`port` default or `fixed`), `context_id` | `context-id: content` only for port source | `value-out: value_type` |
| `context_write` | `value_type`; optional `context_id_source` (`port` default or `fixed`), `context_id` | `value-in: value_type`; `context-id: content` for port source | `context-id: content`, `value-out: value_type` |
| `session_create` | `value_type` (built-in only) | `initial-value: value_type` | `session-id: content` |
| `session_read` | `value_type` (built-in only) | `session-id: content` | `value-out: value_type` |
| `session_write` | `value_type` (built-in only) | `session-id: content`, `value-in: value_type` | `session-id: content`, `value-out: value_type` |
| `workflow` | `workflow_name` | `workflow:<name>` for each snapshotted input | `workflow:<name>` for each snapshotted output |
| `construct_struct` | `struct_id` | one input per declared Struct field; `dataInputPorts` exactly all field names | `struct-out: struct:<id>` |
| `struct_get` | `struct_id`, `field`; `missing` (error default or fallback), `has_fallback` (boolean) | `struct-in`; add `fallback-in` only for fallback mode; `dataInputPorts` exactly these IDs | `value-out` typed as selected field |
| `struct_update` | `struct_id`, `updates: string[]`, `remove_fields: string[]` | `struct-in` and each updates field; `dataInputPorts` exactly those IDs | `struct-out: struct:<id>` |
| `struct_to_json` | `value_type` (declared struct or list-struct only) | `value-in`; `dataInputPorts: ["value-in"]` | `content-out: content` |
| `json_to_struct` | `value_type` (declared struct or list-struct only) | `content-in`; `dataInputPorts: ["content-in"]` | `value-out: value_type` |

### Dynamic port and node details

- `construct_content.append_items` is a nonempty ordered array. A fixed item is exactly `{"type":"fixed","value":"string"}`. A port item is exactly `{"type":"port","port_id":"nonempty-id"}`. Port IDs are unique; each port item creates a `content` input and the `dataInputPorts` list must match those IDs in order. The node concatenates entries in order; a missing port value is skipped and a non-string runtime value is stringified.
- `construct_map_content.mappings` is a nonempty ordered array with unique nonempty `key` values. A fixed entry is `{"key":"...","value":"..."}` and may include `"value_source":"fixed"`. A port entry is exactly `{"key":"...","value_source":"port","port_id":"..."}`. Port IDs are unique and non-control IDs; `dataInputPorts` must match the port entries. Connected values must be strings. The output preserves entry order.
- `router.branches` may be empty. Each entry has exactly unique nonempty `id` and `name`; `branch$others` is reserved as the always-present fallback port and must not be declared. The router requires string `content-in`, matches it exactly against branch names, and otherwise chooses fallback. Missing content is an error, not fallback.
- `deserialize_json.outputs` keys are unique nonempty JSON object keys; types must be supported built-ins (and only types permitted by the node contract). Each key is also the output port ID.
- `item_type` for list/foreach operations is `content`, `message`, `event`, or a declared `struct:<id>` where allowed. `construct_list` supports only `content`, `message`, `event`; its dynamic `dataInputPorts` is exactly the indexed input IDs. `list_append` supports those plus declared Struct; `foreach` likewise. `list_append` and foreach list ports are exactly `list-<item_type>`.
- `history.event_types` is a nonempty unique subset of `terminal`/`response`; `limit` is an integer from 1 to 1000.
- `llm.model` must be a real enabled model ID in the target runtime. The skill cannot know the live model catalog. `llm.tools` names must refer to registered declarations; model-generated tool calls are not automatically executed. `available-tools-in`, when used, is `list-content` and replaces the configured default tool list.
- If `llm.tool_calls` is true, include `available-tools-in` only when dynamically selecting among registered tool names; otherwise configured/default tool selection applies. If it is false, do not declare the dynamic port or `tool_calls` output. If `llm.think` is true, declare `reasoning`; otherwise do not.
- `json_tool` is branch-capable. It uses dynamically supplied tool-name and arguments JSON text; arguments must parse as an object. On success it returns result JSON text and follows `control-out`. On failure it returns error JSON text; it follows `error-out` only if connected, otherwise the invocation fails. Treat it as branching for the no-merge rule and prohibit it in foreach bodies.
- Prefer the current unified `tool` node only when its tool is known to exist. Each port is exactly `{"name":"...","type":"built-in-type"}`; each side permits at most 50 ports. Tool declarations in `metadata.tools` have exact fields `name`, `kind` (`local` or `remote`), `input_ports`, `output_ports`, with unique names. A node's parameters/outputs must exactly match its declaration. Local tool parameters are content. `remote_async_tool` only supports remote declarations and has no `outputs` or `mode`. Do not invent registrations to make an unknown tool appear available.
- `remote_async_tool.callback`, if used, has exact keys `type`, `queue`, `event_type`, `on`; `type` is `redis`, queue nonempty and <=256 chars, event_type nonempty and <=128 chars, on is a nonempty unique subset of `working`, `completed`, `failed`. Never guess queue names.
- Remote tool timeouts default to 10000 ms for sync and 600000 ms for async; documented maxima are 10000 ms and 3600000 ms respectively, subject to deployment configuration. Do not set a value beyond the applicable maximum.
- Context types may be built-in or declared local Struct types. Session types are built-in only. Context `context_id_source` is `port` or `fixed`; fixed requires a nonblank `context_id`, port mode reads its dynamic `context-id` input. Context IDs are exact strings and are not trimmed. `context_create.context_id` may be omitted for runtime generation; an explicit ID must be nonblank and unused. Do not use Session or Context as an implicit branch join or loop accumulator without specifying and type-checking the state behavior.
- Struct metadata entries have `id`, `name`, `color`, `fields`, optional `list_color`; IDs/field names use `[A-Za-z_][A-Za-z0-9_]*`. Each field has exactly `name`, `type`, `required` (boolean). IDs unique; references must exist; Struct definitions cannot recursively refer to themselves, directly or indirectly. A field may use a built-in type or declared Struct/list-Struct. `color` is `#RRGGBB`. Struct values are objects with only declared fields, all required fields present, no nulls, recursively type-valid. Struct cannot cross a workflow/tool boundary.
- `struct_get.missing` is `error` or `fallback`; fallback applies only to optional fields and `has_fallback` must match the mode. `struct_update` fields must be declared, unique, updates/removals disjoint, and required fields cannot be removed. Struct node `dataInputPorts` must exactly match the dynamic inputs stated in the catalog.
- `construct_event` and `publish_event` use Event 1.1 values: object with `version:"1.1"`, nonempty `event_type`, and object `payload`. `construct_event.payload-in` is JSON text for an object. `publish_event` dispatches asynchronously to the Agent/workflow queue and does not re-enter this invocation.
- `deserialize_json.outputs` must be nonempty with unique keys and one of the seven built-in data types. The input is a JSON object containing every configured key. Values are type-checked; content values remain strings and other values may be compact-JSON-serialized into content (including null). `list-content` applies that conversion element-wise.
- `construct_list.item_type` permits `content`, `message`, `event`, or declared Struct; `initial_value_count` is 0-20. `dataInputPorts` must be exactly `<item_type>-in-0` through `<item_type>-in-(count-1)`. `list_append.item_type` permits the same types and position is `start` or `end`.

## Topology Construction And Verification

1. Translate the request into workflow input/output ports, decisions, side effects, state lifetime, failure behavior, and continuation conditions. Only ask for missing environment-specific IDs if necessary for a valid output.
2. Choose node types only from the catalog above. Resolve every required argument and every exact port ID before writing connections. For runtime-registered tools and models, use only values explicitly known from the user's request or tool result.
3. Draw control flow first. Use one Input, terminal Output nodes, unique outcomes, and no convergence. Check every branch by comparing complete downstream reachable-node sets. For foreach, prove the body is one-entry, linear, branch-free, and returns only to that same loop.
4. Add data connections only after control flow is valid. Each source must produce the value on the executed path; no implicit casts, JSON conversions, value collection, parallel join, or producer scheduling are assumed. Control edges define order; data edges transfer values.
5. Serialize every required snapshot, `dataInputPorts`, argument, and connection exactly. Use distinct node IDs. Include `metadata: {"structs": [], "tools": []}` when neither is needed. Do not add a child workflow snapshot unless the child and its exact interface are known. Never claim a tool has been run or the JSON accepted by a runtime validator unless that actually happened.
6. Parse/check the final JSON mentally or with an available local JSON capability; ensure there is exactly one complete object, no comments/trailing commas/placeholders, and run the checklist below. Output raw JSON only for generation. If a necessary environment-specific value is genuinely unavailable, ask one focused question rather than emit knowingly unusable JSON.

For another round, end the current path after persisting continuation data and publishing a constructed Event. The queue's consumer binding is external to this workflow; do not pretend the publish node itself creates a loop or consumer. Define idempotency/duplicate handling and finite budgets in the design contract, and include them as data/logic only when supported by actual available nodes.

## Minimal Valid JSON Example

This is a complete, executable-shaped graph using only built-in nodes and types. It defines one content input and returns it through one Output.

```json
{
  "schema_version": "2.0",
  "name": "echo_input",
  "description": "Returns the supplied text",
  "metadata": {
    "structs": [],
    "tools": []
  },
  "input_ports": [
    {"name": "text", "type": "content"}
  ],
  "output_ports": [
    {"name": "result", "type": "content"}
  ],
  "nodes": [
    {
      "id": "input",
      "type": "input",
      "workflowPorts": [
        {"id": "workflow:text", "name": "text", "type": "content"}
      ]
    },
    {
      "id": "output",
      "type": "output",
      "workflowPorts": [
        {"id": "workflow:result", "name": "result", "type": "content"}
      ]
    }
  ],
  "connections": [
    {
      "fromId": "input",
      "fromPortId": "control-out",
      "toId": "output",
      "toPortId": "control-in",
      "type": "control"
    },
    {
      "fromId": "input",
      "fromPortId": "workflow:text",
      "toId": "output",
      "toPortId": "workflow:result",
      "type": "content"
    }
  ]
}
```

## Final Checklist

- [ ] One complete JSON object, exact Workflow version `2.0`, all required root keys and no unknown keys.
- [ ] Exactly one Input and at least one Output; IDs unique; snapshots exactly match root interfaces.
- [ ] Every node type/argument/port is in this skill's catalog; dynamic port lists and snapshots match their configuration.
- [ ] Every connection has valid endpoints and matching types; no input has multiple data sources; required control ports are connected.
- [ ] Control graph is acyclic apart from valid foreach structured back-edges.
- [ ] No branch-capable node occurs in a foreach body; body is one linear chain back to its own loop.
- [ ] Branch outcomes have pairwise disjoint reachable-node sets and distinct terminal Outputs.
- [ ] Child workflow interfaces are known and exact; no recursive call or Struct boundary leak.
- [ ] Event-driven continuation is a new invocation with explicit state and finite stop condition, not an in-graph cycle.
- [ ] No invented model, registered tool, child workflow, queue, implicit conversion, or runtime guarantee.
