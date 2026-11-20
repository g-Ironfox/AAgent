---
name: workflow-json
description: Design executable AAgent Workflow 2.0 JSON without repository access.
---

# AAgent Workflow JSON Design

Generate complete executable Workflow 2.0 JSON. Assume only this skill and user input are available. This is a durable **process-scheduled** workflow language, not a generic DAG or API sequence. Return valid JSON in one fenced `json` block. Never emit pseudo-nodes, comments, invented types, or runtime process records.

## Missing external facts

Infer ordinary choices conservatively. Ask only when missing information blocks execution or materially changes behavior. Never invent registered Tool names/contracts, required model identifiers, existing child-workflow filenames/contracts, or user approval policy. A dynamic child filename may be supplied at runtime; do not require a static declaration. When creating both parent and child, choose explicit filenames and use them consistently. `metadata.tools` declares an expected contract; it does not register/install a Tool. Ask for missing facts or avoid that dependency. Never claim testing or registration without evidence.

## Process runtime model

A Workflow run is a durable process. A scheduler executes one node at a time from a ready queue and persists progress.

- Waiting nodes return a scheduling request. The process becomes `blocked` with a `wait_for` condition and re-enters the ready queue only on a matching event. Waiting does not occupy a worker.
- `wait_terminal_event` blocks for a **new** user-message event on this process terminal. Earlier messages do not satisfy it. Assistant output does not wake it. It has no data output and does not consume the message.
- `read_terminal_input`, after wake, returns all saved user message bodies in chronological order as `list-content`, not just the waking message.
- `output_to_terminal` appends non-empty text and continues; it does not wake a waiter. Emit a prompt before waiting when appropriate.
- `spawn_and_wait_subprocess` reads a filename and JSON arguments from data inputs, creates a distinct child process and terminal, and blocks the parent until child exit. On success it emits the full result object as JSON text and continues through control-out. Child failure/termination fails the parent.
- The scheduler persists a pending child call. Resume validates results against the child's saved compiled output interface, fills result-json, and advances to the successor without executing the spawn node again or reloading the target file. Do not add a manual restart, polling loop, or Context handoff to return the result. Worker-crash side-effect guarantees remain separate.
- Parent/child may share a public terminal but have separate internal process identities. Never serialize process IDs, wait conditions, scheduler status, compiled graphs, logs, or checkpoints.
- Context is durable cross-node/process state. A process owns Context it creates; a child may access ancestor Context, but parent cannot access a child's Context. Context is cleaned with process termination. Session has separate semantics.
- Active execution timeout excludes blocked/queued time. Do not model human waits as long-running LLM/Tool calls or assume side effects are exactly-once after worker crash.

## Root contract

```json
{
  "schema_version": "2.0",
  "description": "Purpose",
  "metadata": {"structs": [], "tools": [], "functions": []},
  "input_ports": [],
  "output_ports": [],
  "nodes": [],
  "connections": []
}
```

- Required keys: `schema_version`, `input_ports`, `output_ports`, `nodes`, `connections`. Version is string `"2.0"`. Always include `connections`, even empty. Include description and metadata when useful. Do not emit subprocess_workflow_files or workflow_nodes at root or under metadata. No root `name`; filename is external.
- Port is exactly `{ "name":"...", "type":"..." }`; names non-empty and unique per side after trim/case-fold.
- Types: `content` (string), `number` (finite JSON number, not boolean), `list-content` (string array), `map-content` (string-to-string object), `struct:<Id>`, `list-struct:<Id>`. Struct IDs match `[A-Za-z_][A-Za-z0-9_]*` and must be declared in `metadata.structs`.
- Struct is forbidden on root, Tool, and child interfaces. Convert to JSON `content` at those boundaries.
- Node IDs unique/non-empty. Only documented node types, arguments, and fields. Configuration belongs in `arguments`; optional `name`, numeric `x`,`y` are presentation-only. Never include compiled fields (`data_inputs`, `successors`, `_workflow_result`).
- Exactly one `input` and at least one `output`. Their `workflowPorts` mirror root ports exactly and in order: `[{"id":"workflow:<name>","name":"<name>","type":"<type>"}]`.
- Node shape: `{ "id":"...", "type":"...", "arguments":{...} }` plus permitted shared fields; omit empty arguments. Connection shape: `{ "fromId":"...", "fromPortId":"...", "toId":"...", "toPortId":"...", "type":"..." }` (optional `id` omitted). Type is `control` or exact data type at both endpoints.
- At runtime, Input receives values supplied when the process is created. Output collects connected, provided values matching `output_ports` and ends that graph/process frame.

## Control and data

Normal nodes have `control-in`,`control-out`; Input only `control-out`, Output only `control-in`. Control orders execution; data edges propagate values independently.

- Every node is control-reachable from the unique Input. Control graph is a tree: no merges, shared nodes between branches, or cycles except loop-back to its owner.
- Each control output/input has at most one edge. Required control ports connect. Every Router branch, including fallback, connects.
- Each data input has at most one producer. Missing runtime-required input fails; `null` counts as missing. Draw data edges even when control passes through the producer.
- Data may flow from ancestor scope into nested scope, not child-to-parent, between sibling branches, or between loop iterations. Use Context for loop results.
- Branches do not reconverge. Give each terminal branch its own Output or redesign.

### Router

Requires `arguments.branches:[{"id":"branch_id","name":"exact-match"}]`. `content-in:content` selects exact name. Each branch ID is a control output. Fixed `branch$others` fallback is always present and not listed in branches; connect it. No generic `control-out`. Missing/non-string input fails; unmatched string takes fallback.

### Loops

`foreach` and `while_pop` use `control-in`,`loop-out`,`loop-in`,`control-out`. Connect loop-out to first body node and last body node back to this loop's loop-in. Connect control-out to post-loop node. Empty list goes directly to control-out. Body is linear: no Router/multi-output node, Output, shared node, or other entry.

- `foreach`: required `item_type` (`content` or declared `struct:<Id>`); `list-in:list-<item_type>`; `item-out:<item_type>` is in loop scope.
- `while_pop`: required `value_type` (`list-content` or declared `list-struct:<Id>`); pops one item/iteration from a Context-backed list and outputs `item-out` of item type. Defaults `position:"end"`, `context_id_source:"port"`. Port mode requires `context-id:content`; fixed mode requires nonblank `context_id`. It does not output the mutated list.
- If an iteration needs branching or a multi-control-output node, keep the loop body as one `function_call` and put that logic in a local function. Function control flow has its own validated region; do not connect its branches back into the caller except through the declared function return.

## Node reference

Unless noted, nodes use ordinary control ports. Data port names below include types.

| Type | Required arguments | Data ports / semantics |
|---|---|---|
| `input` | none | outputs root `workflow:<name>` |
| `output` | none | inputs root `workflow:<name>`; ends graph |
| `router` | `branches` | `content-in`; special control ports above |
| `construct_message` | none | `content-in` -> `content-out` Message JSON; optional inputs `reasoning-in:content`, `tool-calls-in:list-content` (assistant only), `tool-call-id-in:content` (tool only); optional `role` (system/user/assistant/tool, default user), `role_source` (fixed default or port; port adds `role-in`) |
| `construct_content` | `append_items` | nonempty ordered concat -> `content-out`; items `{type:"fixed",value:string}` or `{type:"port",port_id:string}`; port IDs unique and equal `dataInputPorts`; missing runtime values skipped |
| `construct_map_content` | `mappings` | nonempty mappings -> `map-out`; unique key and fixed string value, or `value_source:"port"` plus unique `port_id`; port IDs equal `dataInputPorts`, runtime values strings |
| `map_content_get` | none | `map-in:map-content`,`key-in:content` -> `content-out:content`; missing key fails |
| `number_to_content` | none | `number-in:number` -> `content-out:content` |
| `output_to_terminal` | none | `content-in:content`; appends nonempty text |
| `wait_terminal_event` | none | no data ports; blocks on new user message; does not return/consume it |
| `read_terminal_input` | none | `list-out:list-content`; all saved user messages oldest-first |
| `deserialize_json` | nonempty `outputs:[{key,type}]` | `content-in` JSON object -> configured outputs; unique keys, built-in types, keys required; non-string content JSON-serialized |
| `construct_list` | `item_type`,`initial_value_count` | count 0..20; inputs `<item_type>-in-N`; `list-out:list-<item_type>`; item type content or declared Struct |
| `list_append` | `item_type`,`position` | `list-in:list-<item_type>`,`item-in:<item_type>` -> same list type; position start/end |
| `list_length` | `value_type` | `list-in` -> `length-out:number`; list-content or declared list-struct |
| `list_get` | `value_type` | `list-in` -> `item-out`; `index_source` default port or fixed; port adds `index-in:number`; fixed requires integer `index` |
| `list_slice` | `value_type` | `list-in` -> same `list-out`; list-content or list-struct. Optional start/stop/step source/value; port adds matching `*-in:number` |
| `construct_tool` | none | outputs `tool-out:content`; optional `tool_name`,`description`,`schema`,`required`, each with optional `<field>_source` (`fixed`/`port`). Port inputs: `name-in`,`description-in`,`schema-in` (JSON Schema text), `required-in:list-content`. Builds one function Tool definition; schema must be an object-parameter JSON Schema |
| `foreach`,`while_pop` | as above | special loop control ports |
| `llm` | none | `messages-in:list-content` (nonempty JSON-string list of `{role,content}`) -> `output:content`; optional `model`,`think`,`tool_calls`,`tools`,`tools_source`. `tool_calls:true` adds `tool_calls:list-content` output and `available-tools-in:list-content` input (or `tools-in:list-content` with `tools_source:"definitions"`). Provider/model external. Generated tool calls are not executed automatically |
| `tool` | `tool`,`parameters:[{name,type}]`,`outputs:[{name,type}]` | synchronous registered Tool. Ports exactly match `metadata.tools` declaration (`kind` local/remote). Optional `mode` only sync, `timeout_ms`, `callback` only null |
| `json_tool` | none | `tool-name:content`,`arguments-json:content` -> `result-json:content` on `control-out`; on exception outputs `error-json:content` and takes `error-out` if connected, otherwise process fails. Invokes a dynamically named registered Local/Remote Tool; it does not create a child process |
| `remote_async_tool` | `tool` | async Remote Tool; declared params, output `task_id:content`; optional parameters/timeout_ms/callback; requires remote declaration; not a workflow subprocess |
| `local_tool` (legacy) | `tool` | optional string-array parameters; each content input; `output:content`. Prefer unified `tool` |
| `remote_sync_tool` (legacy) | `tool` | parameters/outputs port arrays, optional timeout_ms. Prefer unified `tool` |
| `context_create` | `value_type` | `initial-value:<type>` -> `context-id:content`; optional nonblank unique `context_id`; omit to generate |
| `context_read` | `value_type` | -> `value-out:<type>`; default port ID mode requires `context-id:content`; fixed mode requires nonblank `context_id` |
| `context_write` | `value_type` | `value-in:<type>` and port-mode context-id -> `context-id:content`,`value-out:<type>`; ID mode as context_read |
| `session_create` | `value_type` | `initial-value:<type>` -> `session-id:content` |
| `session_read` | `value_type` | `session-id:content` -> `value-out:<type>` |
| `session_write` | `value_type` | `session-id:content`,`value-in:<type>` -> `session-id:content`,`value-out:<type>` |
| `spawn_and_wait_subprocess` | none | `workflow-file:content`, `arguments-json:content` -> `result-json:content`; normal control ports; creates and waits for a child process |

## Contracts and composition

- Struct entry: `{"id":"Record","name":"Record","color":"#336699","fields":[{"name":"title","type":"content","required":true}]}`. IDs/field names use identifier syntax; fields unique; types built-in or declared Struct; recursion forbidden. Struct values are validated objects; list-struct is a list of objects.
- Struct nodes if needed: `construct_struct` (`struct_id`, required fields by name -> `struct-out`); `struct_get` (`struct_id`,`field`, optional `missing:"error"|"fallback"`, `has_fallback` default false; `struct-in`, optional `fallback-in` -> `value-out`); `struct_update` (`struct_id`, optional `updates`,`remove_fields`; `struct-in` -> `struct-out`); `struct_to_json` (`value_type`,`value-in` -> JSON `content-out`); `json_to_struct` (`value_type`,`content-in` -> `value-out`). Declare Struct first.
- Context allows built-in/declared Struct; Session built-in only. Context IDs are exact strings, never normalize. Port mode default; fixed mode has no ID input and requires nonblank `context_id`.
- Tool declaration: `metadata.tools:[{"name":"...","kind":"local|remote","input_ports":[{"name":"...","type":"content"}],"output_ports":[{"name":"...","type":"content"}]}]`. Types only content/number/list-content/map-content; no Struct/control names. Declaration is not proof of registration; node arrays copy it exactly.
- `llm.messages-in` is a list of JSON-encoded messages, not a raw prompt. Build via `construct_message` and compatible list flow; use a system message for system instructions. Exact model/provider is external.
- To save an assistant turn, use one `construct_message(role="assistant")`: connect LLM `output` (normalize null to empty content if necessary) to `content-in`, `reasoning` to `reasoning-in`, and `tool_calls` directly to `tool-calls-in`. The call input is a list of JSON strings; the node parses each into an object, preserving call IDs and argument strings. Empty calls and absent optional inputs are omitted. Reasoning is retained even without calls. Do not build different message shapes using a required-field Struct and a plain-message branch.
- For a tool result, use `construct_message(role="tool")` with result text on `content-in` and the original assistant call ID on `tool-call-id-in`. Always supply this ID for native tool results. Optional message fields are role-specific; passing reasoning/calls to a non-assistant, or a tool-call ID to a non-tool, fails. Existing role/content-only messages remain supported.
- LLM tools may come from `metadata.tools` (`tools_source:"declared"`, the default) or complete function definitions supplied as JSON strings in `tools-in:list-content` (`tools_source:"definitions"`). The latter does not require pre-registration when merely offered to the model. To execute a model-selected call, explicitly route/parse and invoke a Tool node or `json_tool`; `llm.tool_calls` alone only returns call descriptions. `json_tool` success/error control branches are separate scopes, so never pass data from one branch into the other or out to a parent scope.
- Local functions are not processes. Declare `metadata.functions` entries `{id,name,input_ports,output_ports}`. Each has exactly one `function_input` and at least one `function_output`, with top-level `function_id` matching declaration. Control goes entry-to-return. Call with `function_call` and `arguments.function_id`; data ports `function:<name>`. Each invocation has isolated state; return only via function outputs. No recursive calls; each node belongs to one main/function region.
## Child workflows and terminal interaction

- Use one node: `{"id":"call-child","type":"spawn_and_wait_subprocess","arguments":{}}` (empty arguments may be omitted). Connect normal control-in/control-out. It has no configuration fields, child declarations, or input_ports/output_ports snapshots. Old workflow_file/workflow_name arguments and per-port calls require explicit JSON rewiring; removing old declarations alone does not convert them.
- Connect `workflow-file:content` to an exact workspace filename including its extension (nonblank, at most 200 characters). Preserve the exact string; do not substitute a repository path. Supply it from a parent input or a construct_content node with a fixed filename. Runtime loading checks the target and rejects recursive calls.
- Connect `arguments-json:content` to JSON **object text**, for example `{"name":"小明"}`. Keys match the target's root input_ports names; unknown keys or non-null values of the wrong type fail. Missing/null values count as unprovided. With dynamic targets, validation uses the interface loaded at call time, not an author-time snapshot. An empty input interface still needs `{}` text.
- `result-json:content` contains the full child output object as JSON text, for example `{"reply":"你好，小明！"}`. The child receives values through Input and returns through Output. To extract reply, use deserialize_json with `arguments:{"outputs":[{"key":"reply","type":"content"}]}`, connect result-json to content-in, and use its reply output. Forward result-json directly when the full object is wanted.
- For dynamic JSON parameters, build a declared Struct and serialize with struct_to_json, or use an already serialized object input. Do not concatenate arbitrary user strings into JSON; quotes and newlines need correct escaping. Struct values must be serialized before crossing the process interface. Context remains available for explicit shared state; result-json already handles the return value.
- When the requested workflow is interactive, connect terminal nodes explicitly. A runnable one-message pattern is: prompt via output_to_terminal → wait_terminal_event → read_terminal_input → list_get with `arguments:{"value_type":"list-content","index_source":"fixed","index":-1}` → spawn_and_wait_subprocess → deserialize_json → output_to_terminal → Output. Connect the terminal reader's list-out to list-in, the selected item-out to arguments-json, and a filename producer to workflow-file. The prompt should ask for a JSON object such as `{"name":"小明"}`; print the decoded reply in the parent terminal. This handles one message and ends; do not imply it is a continuing chat loop. Prompt and filename text need actual producers and control edges.
- Terminal I/O serves user interaction; child Input/Output serves process parameters and results. A child does not need to reread terminal history to receive arguments, and printing to its terminal does not return a value to the parent. Keep Input and Output boundary nodes even for terminal-driven workflows, using empty root input_ports when creation-time inputs are unnecessary.

## Design and validation

1. Extract purpose, inputs, outputs, dependencies, side effects, interaction, failure, repetition, and stop conditions.
2. Resolve only necessary external facts; make other reasonable choices.
3. Choose the smallest structure: ordinary nodes, Router, finite Foreach, Context, terminal wait+read, or a real subprocess.
4. Declare ports, Structs, Tool contracts, and local functions before nodes. Child calls use fixed JSON ports and runtime filename/argument producers; do not declare child snapshots.
5. Sketch control tree first; independently terminate branches. Add loop-backs, then typed data edges.
6. Check node arguments/ports/types, persistence over waits, and behavior on every path.
7. Without validator/runtime, say the result is statically reasoned, not executed.

Final checklist:

- [ ] Pure valid JSON; version exactly `"2.0"`; required root keys present.
- [ ] Exactly one Input, at least one Output; unique IDs; supported nodes/arguments only.
- [ ] Root snapshots exact and ordered; no Struct on public interfaces.
- [ ] Required controls connected; every node reachable; no merge/illegal cycle; Router branches and fallback terminate separately.
- [ ] Loop body linear and returns to owner; no Router/Output/branching; item does not escape scope.
- [ ] Data endpoints/types match; no duplicate producer or illegal cross-scope edge.
- [ ] Runtime-required values exist on all paths and match JSON types.
- [ ] Terminal wait has an appropriate prompt and explicit read after wake.
- [ ] Context/Session types and ID modes correct; loop results use Context as needed.
- [ ] External dependencies supplied or resolved at runtime; Tool/function declarations match; no fabricated registration claims.
- [ ] Child calls have workflow-file and JSON object text on arguments-json, consume result-json, and contain no legacy declarations, filename arguments, or interface snapshots.
- [ ] Output, empty-input, branch, and failure behavior meet request.

If a blocking external fact is missing, ask a focused question instead of fabricating an executable workflow. Add a concise note for assumptions or unverified dependencies.
