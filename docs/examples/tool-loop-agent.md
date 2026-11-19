# Tool-Loop Agent

`tool-loop-agent.flow` is a Workflow 2.0 example of an automatically executing ReAct agent. It uses the process scheduler, native LLM tool calls, Context-backed conversation history, `while_pop`, and local functions. The model can choose `ask_human` to ask for clarification or a decision and wait for user input. No protocol or runtime changes are needed.

## Setup

1. Import `tool-loop-agent.flow` into the workspace.
2. Select an enabled model that supports native tool calls in the `llm` node, replacing `REPLACE_WITH_MODEL_ID`.
3. Create a process with a `task` input, for example: `Find the project configuration file, inspect it, and summarize the relevant settings.`
4. When the agent asks a question, wait until the process shows `blocked` / waiting for terminal input, then reply in that process terminal. The tool result resumes the model loop.
5. Read the final answer in the process terminal.

The example offers the existing Local Tools `workspace.list_files` and `workspace.get_file`, plus the workflow-handled `ask_human` tool. The workspace tools must be registered in the runtime. Three `construct_tool` nodes assemble the definitions supplied to `llm.tools-in` with `tools_source: "definitions"`. `ask_human` is dispatched inside `run_one_tool`; it does not require a registered Local Tool. To change executable tools, update their definitions, `metadata.tools`, and any dispatch branches together, preserving parameter and output contracts. Tool declarations do not install tools.

## Execution

The root process initializes a message-history Context and a one-item turn queue. `while_pop` schedules a `tool_loop_turn` function and blocks between ready-queue steps. Each turn reads history, calls the model, and saves a native assistant message, including structured tool calls and reasoning content. A single `construct_message` builds assistant messages for both ordinary replies and tool calls, retaining reasoning even when there are no calls. Its `tool-calls-in` port accepts the LLM's JSON-string list and writes an object array; empty calls are omitted. Tool results use the same node with `tool-call-id-in`. Message construction requires no Assistant or ToolMessage Struct.

- With no tool calls, the turn writes the model's final response to the process terminal and does not add another queue token. The loop then ends and the process completes.
- With one or more calls, a `foreach` invokes a `run_one_tool` local function for each call in order. Workspace calls are dispatched through `json_tool`; success or failure is recorded as a `tool` message with the matching `tool_call_id`. After the batch, another turn token is added so the model can inspect observations and decide what to do next.
- When the model calls `ask_human({"question": "..."})`, the workflow reads terminal input and records its `list_length` before displaying the question. `wait_terminal_event` suspends the process and its function stack. After a terminal event, the workflow reads input again and uses `list_slice(start=previous_length)` to obtain only new replies. It serializes all those replies as `{"replies": ["..."]}` into a `role: "tool"` message matching the original `tool_call_id`; older messages are excluded.
- After `ask_human`, remaining calls in that model batch are recorded as skipped, each with a matching tool result. The next model turn can use the reply to plan fresh tool calls. Calls already executed earlier in the batch remain executed. The batch flag resets on every model turn.
- JSON Tool's branching logic is kept inside a local function. The loop body itself remains a single `function_call`, satisfying Workflow lifecycle validation.

The loop ends when the model returns no tool calls. There is no separate maximum-turn setting in this example; active execution remains subject to the runtime's configured process execution limit. Workspace tool calls execute automatically. The model chooses when to ask the human; `ask_human` replies are observations, not a separate approval gate. If the model returns no tool calls, the process completes instead of waiting for unsolicited follow-up input. Use only in a runtime whose available Tools and permissions are appropriate for that policy.

The input cursor uses existing list nodes; no scheduler or terminal message protocol changes are required. Under the existing runtime, terminal events wake processes that are already blocked. Submit replies after the wait state appears; early input is not guaranteed to wake a subsequent wait. If several replies arrive before input is read, all entries after the cursor are returned in order. An empty slice is represented by `{"replies": []}`, allowing the model to ask again.

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

Tests cover static validation, multiple tool calls, errors, human wait/resume, skipped batch calls, old input exclusion, multiple replies, and repeated questions. They use the real static validator and in-memory process scheduler with mocked model/tool/terminal calls; they do not contact a real model or external Tool Server.

From the repository root, the editor serialization regression can be checked with:

```powershell
node --test workflow_editor/test_tool_loop_workflow.mjs
```
