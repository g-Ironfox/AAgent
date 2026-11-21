"""Build an editable ALFWorld ReAct agent, action-only agent, or IO smoke test."""

import argparse
import json
from pathlib import Path

from build_react_workflow import Graph


PROMPT = """You are acting in the ALFWorld text environment. Solve the household task
from the initial observation, retaining previous observations and actions.
Return exactly one executable ALFWorld command as plain text. Do not output
reasoning, JSON, markdown, or a prefix. Typical commands include: look,
inventory, go to <receptacle>, open <receptacle>, take <object> from <receptacle>,
put <object> in/on <receptacle>, clean <object> with <receptacle>,
heat <object> with <receptacle>, cool <object> with <receptacle>,
use <object>. Use the object and receptacle IDs in the observations.
The user sends JSON observations; optional admissible_commands are available
only when the evaluator explicitly enables that setting."""


REACT_PROMPT = """You are acting in the ALFWorld text environment. Solve the household task
from the initial observation using a reasoning, action, observation loop.
The user sends one JSON observation per turn. Use the complete history to track
the task, locations, inventory, and results of previous actions. Reason using the
model's reasoning channel, then return exactly one executable ALFWorld command
as plain text in the final response, for example: open cabinet 1
Do not include reasoning, JSON, markdown, a prefix, or multiple commands in the
final response. Only the final response is executed by the environment.
Typical commands include: look, inventory, go to <receptacle>, open <receptacle>,
close <receptacle>, take <object> from <receptacle>, put <object> in/on <receptacle>,
clean <object> with <receptacle>, heat <object> with <receptacle>,
cool <object> with <receptacle>, use <object>.
Use the exact object and receptacle IDs from observations. Inspect likely locations,
open closed receptacles before searching them, and revise your plan if an action
fails. Optional admissible_commands are provided only when the evaluator enables
that setting; when present, choose an action from that list.
"""

REACT_MODEL_ID = "REPLACE_WITH_MODEL_ID"


def build_workflow(model_id=None, *, react=False):
    if react:
        model_id = model_id or REACT_MODEL_ID
    g = Graph()
    if react:
        description = "ALFWorld minimal ReAct: native reasoning, action, observation with durable history"
    elif model_id:
        description = "ALFWorld terminal loop"
    else:
        description = "ALFWorld IO smoke test: always look; does not solve tasks"
    g.doc.update(description=description, input_ports=[], output_ports=[],
                 metadata={"structs": [], "functions": [], "tools": []})
    g.node("start", "input", workflowPorts=[])
    g.const("token", "next")
    g.node("initial_tokens", "construct_list", arguments={"item_type": "content", "initial_value_count": 1}, dataInputPorts=["content-in-0"])
    g.data("token", "content-out", "initial_tokens", "content-in-0")
    g.ctx("tokens", "create")
    g.data("initial_tokens", "list-out", "tokens", "initial-value", "list-content")
    g.node("turn_gate", "while_pop", arguments={"value_type": "list-content", "position": "start", "context_id_source": "port"})
    g.data("tokens", "context-id", "turn_gate", "context-id")
    bindings = {"tokens_id": ("tokens", "context-id")}
    if model_id:
        g.const("system_text", REACT_PROMPT if react else PROMPT)
        g.node("system", "construct_message", arguments={"role": "system"})
        g.data("system_text", "content-out", "system", "content-in")
        g.node("initial", "construct_list", arguments={"item_type": "content", "initial_value_count": 1}, dataInputPorts=["content-in-0"])
        g.data("system", "content-out", "initial", "content-in-0")
        g.ctx("history", "create")
        g.data("initial", "list-out", "history", "initial-value", "list-content")
        g.chain("start", "system_text", "system", "initial", "history", "token")
        bindings["history_id"] = ("history", "context-id")
    else:
        g.control("start", "token")
    g.chain("token", "initial_tokens", "tokens", "turn_gate")
    g.call("turn", "alfworld_turn", bindings)
    g.node("out", "output", workflowPorts=[])
    g.control("turn_gate", "turn", "loop-out")
    g.control("turn", "turn_gate", inp="loop-in")
    g.control("turn_gate", "out")
    function_inputs = [("tokens_id", "content")]
    if model_id:
        function_inputs.append(("history_id", "content"))
    fi = g.function("alfworld_turn", function_inputs)
    g.node("read", "read_terminal_queue")
    g.control(fi, "read")
    g.node("latest", "list_get", arguments={"value_type": "list-content", "index_source": "fixed", "index": -1})
    g.data("read", "list-out", "latest", "list-in", "list-content")
    g.node("parse", "deserialize_json", arguments={"outputs": [
        {"key": "episode_id", "type": "content"}, {"key": "step", "type": "number"},
        {"key": "done", "type": "content"},
    ]})
    g.data("latest", "item-out", "parse", "content-in")
    g.node("done", "router", arguments={"branches": [{"id": "finish", "name": "true"}]})
    g.data("parse", "done", "done", "content-in")
    g.ret("end", "alfworld_turn")
    g.control("done", "end", "finish")
    g.chain("read", "latest", "parse", "done")
    if model_id:
        g.node("user", "construct_message", arguments={"role": "user"})
        g.data("latest", "item-out", "user", "content-in")
        g.ctx("history_read", "read")
        g.data(fi, "function:history_id", "history_read", "context-id")
        g.node("append_user", "list_append", arguments={"item_type": "content", "position": "end"})
        g.data("history_read", "value-out", "append_user", "list-in", "list-content")
        g.data("user", "content-out", "append_user", "item-in")
        g.node("decide", "llm", arguments={"model": model_id, "think": react, "tool_calls": False, "tools_source": "definitions"})
        g.data("append_user", "list-out", "decide", "messages-in", "list-content")
        g.node("assistant", "construct_message", arguments={"role": "assistant"})
        g.data("decide", "output", "assistant", "content-in")
        if react:
            g.data("decide", "reasoning", "assistant", "reasoning-in")
        g.node("append_assistant", "list_append", arguments={"item_type": "content", "position": "end"})
        g.data("append_user", "list-out", "append_assistant", "list-in", "list-content")
        g.data("assistant", "content-out", "append_assistant", "item-in")
        g.ctx("history_write", "write")
        g.data(fi, "function:history_id", "history_write", "context-id")
        g.data("append_assistant", "list-out", "history_write", "value-in", "list-content")
        g.control("done", "user", "branch$others")
        g.chain("user", "history_read", "append_user", "decide", "assistant", "append_assistant", "history_write")
        last, action_source = "history_write", ("decide", "output")
    else:
        g.const("look", "look")
        g.control("done", "look", "branch$others")
        last, action_source = "look", ("look", "content-out")
    g.const("action_type", "action")
    g.struct("AlfworldAction", [("type", "content"), ("episode_id", "content"), ("step", "number"), ("text", "content")])
    g.make_struct("action", "AlfworldAction", {
        "type": ("action_type", "content-out", "content"),
        "episode_id": ("parse", "episode_id", "content"),
        "step": ("parse", "step", "number"), "text": (*action_source, "content"),
    })
    g.node("serialize", "struct_to_json", arguments={"value_type": "struct:AlfworldAction"})
    g.data("action", "struct-out", "serialize", "value-in", "struct:AlfworldAction")
    g.node("send", "output_to_terminal")
    g.data("serialize", "content-out", "send", "content-in")
    g.ctx("tokens_read", "read")
    g.data(fi, "function:tokens_id", "tokens_read", "context-id")
    g.const("next_token", "next")
    g.node("tokens_append", "list_append", arguments={"item_type": "content", "position": "end"})
    g.data("tokens_read", "value-out", "tokens_append", "list-in", "list-content")
    g.data("next_token", "content-out", "tokens_append", "item-in")
    g.ctx("tokens_write", "write")
    g.data(fi, "function:tokens_id", "tokens_write", "context-id")
    g.data("tokens_append", "list-out", "tokens_write", "value-in", "list-content")
    g.ret("continue", "alfworld_turn")
    g.chain(last, "action_type", "action", "serialize", "send", "tokens_read", "next_token", "tokens_append", "tokens_write", "continue")
    # Keep the loop readable on the workflow canvas.
    for index, node in enumerate(g.doc["nodes"]):
        node.update(x=80 + (index % 5) * 280, y=100 + (index // 5) * 240)
    return g.doc


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-id", help="Enabled model ID from the manager WebUI")
    parser.add_argument("--react", action="store_true", help="Use native reasoning and execute one action per observation")
    parser.add_argument("--output", type=Path, help="Destination .flow file (default: docs/examples/alfworld-look.flow or alfworld-react.flow with --react)")
    args = parser.parse_args()
    if args.output is None:
        example = "alfworld-react.flow" if args.react else "alfworld-look.flow"
        args.output = Path(__file__).resolve().parents[1] / "docs/examples" / example
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(build_workflow(args.model_id, react=args.react), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(args.output)
