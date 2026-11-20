# Tool-Loop Agent

`tool-loop-agent.flow` is a Workflow 2.0 example of an automatically executing ReAct agent. It uses the process scheduler, native LLM tool calls, Context-backed conversation history, `while_pop`, and local functions. The model can choose `ask_human` to ask for clarification or a decision and wait for user input. No protocol or runtime changes are needed.

## Setup

1. Import `tool-loop-agent.flow` into the workspace.
2. Select an enabled model that supports native tool calls in the `llm` node, replacing `REPLACE_WITH_MODEL_ID`.
3. Create a process with a `task` input, for example: `Find the project configuration file, inspect it, and summarize the relevant settings.`
4. When the agent asks a question, reply in that process terminal; replies arriving before the queue read are buffered. The tool result resumes the model loop.
5. Read the final answer in the process terminal.

The example offers the existing Local Tools `workspace.list_files` and `workspace.get_file`, plus the workflow-handled `ask_human` tool. The workspace tools must be registered in the runtime. Three `construct_tool` nodes assemble the definitions supplied to `llm.tools-in` with `tools_source: "definitions"`. `ask_human` is dispatched inside `run_one_tool`; it does not require a registered Local Tool. To change executable tools, update their definitions, `metadata.tools`, and any dispatch branches together, preserving parameter and output contracts. Tool declarations do not install tools.

## Execution

The root process initializes a message-history Context and a one-item turn queue. `while_pop` schedules a `tool_loop_turn` function and blocks between ready-queue steps. Each turn reads history, calls the model, and saves a native assistant message, including structured tool calls and reasoning content. A single `construct_message` builds assistant messages for both ordinary replies and tool calls, retaining reasoning even when there are no calls. Its `tool-calls-in` port accepts the LLM's JSON-string list and writes an object array; empty calls are omitted. Tool results use the same node with `tool-call-id-in`. Message construction requires no Assistant or ToolMessage Struct.

- With no tool calls, the turn writes the model's final response to the process terminal and does not add another queue token. The loop then ends and the process completes.
- With one or more calls, a `foreach` invokes a `run_one_tool` local function for each call in order. Workspace calls are dispatched through `json_tool`; success or failure is recorded as a `tool` message with the matching `tool_call_id`. After the batch, another turn token is added so the model can inspect observations and decide what to do next.
- When the model calls `ask_human({"question": "..."})`, the workflow displays the question and executes `read_terminal_queue`. It consumes all pending replies from the terminal process buffer in arrival order, or suspends the process and its function stack if the queue is empty. A terminal event appends its content and wakes the waiting process to retry the same read node. It serializes the batch as `{"replies": ["..."]}` into a `role: "tool"` message matching the original `tool_call_id`. Previously consumed replies are excluded.
- After `ask_human`, remaining calls in that model batch are recorded as skipped, each with a matching tool result. The next model turn can use the reply to plan fresh tool calls. Calls already executed earlier in the batch remain executed. The batch flag resets on every model turn.
- JSON Tool's branching logic is kept inside a local function. The loop body itself remains a single `function_call`, satisfying Workflow lifecycle validation.

The loop ends when the model returns no tool calls. There is no separate maximum-turn setting in this example; active execution remains subject to the runtime's configured process execution limit. Workspace tool calls execute automatically. The model chooses when to ask the human; `ask_human` replies are observations, not a separate approval gate. If the model returns no tool calls, the process completes instead of waiting for unsolicited follow-up input. Use only in a runtime whose available Tools and permissions are appropriate for that policy.

The terminal buffer is stored in the terminal process's kernel Redis record. Consuming a batch and saving node progress use the same transaction, so a failed commit leaves the batch pending. Input arriving between the empty check and suspension prevents the process from remaining blocked. Messages appended after a batch was read remain for the next read. MongoDB terminal history is used only for WebUI display; the workflow no longer needs history-length cursors or list slicing.

Conversation history and loop state are held in process Context. Terminal output and scheduler persistence follow the normal process model. This does not add automatic recovery after arbitrary worker crashes or exactly-once guarantees for external side effects.

## Regenerate and verify

From the repository root:

```powershell
python scripts/build_tool_loop_workflow.py
```

From `agent/`:

```powershell
python -m unittest test_tool_loop_workflow -v
```

Tests cover static validation, multiple tool calls, errors, human wait/resume, skipped batch calls, consumed input exclusion, multiple replies, and repeated questions. They use the real static validator and in-memory process scheduler with mocked model/tool calls; they do not contact a real model or external Tool Server.

From the repository root, the editor serialization regression can be checked with:

```powershell
node --test workflow_editor/test_tool_loop_workflow.mjs
```
