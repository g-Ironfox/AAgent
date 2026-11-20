"""Build a durable, automatically executing native-tool ReAct workflow."""
from pathlib import Path
import json


class Graph:
    def __init__(self):
        self.doc = {
            "schema_version": "2.0",
            "description": "Process-scheduled tool-loop agent with optional ask_human interaction and durable conversation history.",
            "input_ports": [{"name": "task", "type": "content"}],
            "output_ports": [],
            "metadata": {
                "structs": [],
                "functions": [],
                "tools": [
                    {"name": "workspace.list_files", "kind": "local", "input_ports": [],
                     "output_ports": [{"name": "items", "type": "list-content"}, {"name": "revision", "type": "number"}]},
                    {"name": "workspace.get_file", "kind": "local",
                     "input_ports": [{"name": "file_id", "type": "content"}],
                     "output_ports": [{"name": "output", "type": "content"}]},
                ],
            },
            "nodes": [],
            "connections": [],
        }
        self.lane = 0
        self.column = 0

    def node(self, node_id, node_type, **fields):
        self.doc["nodes"].append({
            "id": node_id,
            "type": node_type,
            "name": fields.pop("name", node_id.replace("_", " ")),
            "x": 80 + 260 * self.column,
            "y": 100 + 600 * self.lane,
            **fields,
        })
        self.column += 1
        return node_id

    def function(self, name, inputs, outputs=()):
        self.doc["metadata"]["functions"].append({
            "id": name, "name": name,
            "input_ports": ports(inputs), "output_ports": ports(outputs),
        })
        self.lane += 1
        self.column = 0
        return self.node(name + "_in", "function_input", function_id=name)

    def ret(self, node_id, function):
        return self.node(node_id, "function_output", function_id=function)

    def data(self, source, out_port, target, in_port, kind="content"):
        self.doc["connections"].append({
            "fromId": source, "fromPortId": out_port,
            "toId": target, "toPortId": in_port, "type": kind,
        })

    def control(self, source, target, out_port="control-out", in_port="control-in"):
        self.data(source, out_port, target, in_port, "control")

    def chain(self, *node_ids):
        for source, target in zip(node_ids, node_ids[1:]):
            self.control(source, target)

    def const(self, node_id, value):
        return self.node(node_id, "construct_content", arguments={
            "append_items": [{"type": "fixed", "value": value}],
        }, dataInputPorts=[])

    def text(self, node_id, prefix="", suffix=""):
        return self.node(node_id, "construct_content", arguments={
            "append_items": [
                {"type": "fixed", "value": prefix},
                {"type": "port", "port_id": "value"},
                {"type": "fixed", "value": suffix},
            ],
        }, dataInputPorts=["value"])

    def ctx(self, node_id, operation, value_type="list-content"):
        return self.node(node_id, "context_" + operation, arguments={"value_type": value_type})

    def call(self, node_id, function, bindings):
        self.node(node_id, "function_call", arguments={"function_id": function})
        for name, source in bindings.items():
            self.data(*source[:2], node_id, "function:" + name,
                      source[2] if len(source) == 3 else "content")
        return node_id

    def struct(self, name, fields):
        self.doc["metadata"]["structs"].append({
            "id": name, "name": name, "color": "#3976A8",
            "fields": [{"name": field, "type": kind, "required": True} for field, kind in fields],
        })

    def make_struct(self, node_id, struct_id, bindings):
        self.node(node_id, "construct_struct", arguments={"struct_id": struct_id},
                  dataInputPorts=list(bindings))
        for field, (source, out_port, kind) in bindings.items():
            self.data(source, out_port, node_id, field, kind)
        return node_id

    def get(self, node_id, struct_id, field, source, out_port="struct-out"):
        self.node(node_id, "struct_get", arguments={"struct_id": struct_id, "field": field},
                  dataInputPorts=["struct-in"])
        self.data(source, out_port, node_id, "struct-in", "struct:" + struct_id)
        return node_id


def ports(items):
    return [{"name": name, "type": type_name} for name, type_name in items]


def build_workflow():
    g = Graph()
    g.struct("ToolCallCount", [("count", "number")])
    g.struct("CallFunction", [("name", "content"), ("arguments", "content")])
    g.struct("ToolCall", [("id", "content"), ("type", "content"), ("function", "struct:CallFunction")])
    g.struct("AskHumanArgs", [("question", "content")])
    g.struct("HumanReply", [("replies", "list-content")])
    n, d = g.node, g.data
    p = lambda node, name: (node, "function:" + name)

    # Root process initializes durable history and a one-item scheduling loop.
    n("in", "input", workflowPorts=[{"id": "workflow:task", "name": "task", "type": "content"}])
    prompt = g.const("system_prompt", "You are a ReAct assistant. Respond in the user's language. Use only the provided tools and their declared schemas when needed. Tool calls are executed automatically, so use them only when they are necessary and safe. Call ask_human when you need clarification, a decision, or information only the user can provide. Put a clear, non-empty question in its question argument, in the user's language. Ask one focused question at a time. The result contains only new human replies; an empty replies list means no new answer was available. After ask_human, remaining calls in that batch are skipped so you can replan. After receiving tool results, continue reasoning and call more tools if needed. When no more tools are needed, give a concise, accurate final answer. Never claim an unexecuted action succeeded.")
    n("system", "construct_message", arguments={"role": "system"})
    d(prompt, "content-out", "system", "content-in")
    n("task_message", "construct_message", arguments={"role": "user"})
    d("in", "workflow:task", "task_message", "content-in")
    n("initial_history", "construct_list", arguments={"item_type": "content", "initial_value_count": 2},
      dataInputPorts=["content-in-0", "content-in-1"])
    d("system", "content-out", "initial_history", "content-in-0")
    d("task_message", "content-out", "initial_history", "content-in-1")
    g.ctx("create_history", "create")
    d("initial_history", "list-out", "create_history", "initial-value", "list-content")
    token = g.const("start_token", "next")
    n("initial_tokens", "construct_list", arguments={"item_type": "content", "initial_value_count": 1},
      dataInputPorts=["content-in-0"])
    d(token, "content-out", "initial_tokens", "content-in-0")
    g.ctx("create_tokens", "create")
    d("initial_tokens", "list-out", "create_tokens", "initial-value", "list-content")
    n("turn_gate", "while_pop", arguments={"value_type": "list-content"})
    d("create_tokens", "context-id", "turn_gate", "context-id")
    g.call("call_turn", "tool_loop_turn", {
        "history_id": ("create_history", "context-id"),
        "tokens_id": ("create_tokens", "context-id"),
    })
    n("out", "output", workflowPorts=[])
    g.chain("in", prompt, "system", "task_message", "initial_history", "create_history",
            "start_token", "initial_tokens", "create_tokens", "turn_gate")
    g.control("turn_gate", "call_turn", "loop-out")
    g.control("call_turn", "turn_gate", in_port="loop-in")
    g.control("turn_gate", "out")

    # Appending history is a small local function so callers stay linear.
    fi = g.function("append_history", [("history_id", "content"), ("message", "content")])
    g.ctx("history_read", "read"); d(*p(fi, "history_id"), "history_read", "context-id")
    n("history_append", "list_append", arguments={"item_type": "content", "position": "end"})
    d("history_read", "value-out", "history_append", "list-in", "list-content")
    d(*p(fi, "message"), "history_append", "item-in")
    g.ctx("history_write", "write")
    d(*p(fi, "history_id"), "history_write", "context-id")
    d("history_append", "list-out", "history_write", "value-in", "list-content")
    g.ret("history_return", "append_history")
    g.chain(fi, "history_read", "history_append", "history_write", "history_return")

    fi = g.function("queue_turn", [("tokens_id", "content")])
    g.ctx("tokens_read", "read"); d(*p(fi, "tokens_id"), "tokens_read", "context-id")
    g.const("next_token", "next")
    n("tokens_append", "list_append", arguments={"item_type": "content", "position": "end"})
    d("tokens_read", "value-out", "tokens_append", "list-in", "list-content")
    d("next_token", "content-out", "tokens_append", "item-in")
    g.ctx("tokens_write", "write")
    d(*p(fi, "tokens_id"), "tokens_write", "context-id")
    d("tokens_append", "list-out", "tokens_write", "value-in", "list-content")
    g.ret("tokens_return", "queue_turn")
    g.chain(fi, "tokens_read", "next_token", "tokens_append", "tokens_write", "tokens_return")

    # Preserve native assistant tool_calls as structured API history.
    fi = g.function("build_assistant", [("content", "content"), ("reasoning", "content"), ("calls", "list-content")], [("message", "content")])
    n("build_message", "construct_message", arguments={"role": "assistant"})
    d(*p(fi, "content"), "build_message", "content-in")
    d(*p(fi, "reasoning"), "build_message", "reasoning-in")
    d(*p(fi, "calls"), "build_message", "tool-calls-in", "list-content")
    g.ret("build_return", "build_assistant")
    d("build_message", "content-out", "build_return", "function:message")
    g.chain(fi, "build_message", "build_return")

    fi = g.function("record_tool_result", [("history_id", "content"), ("call_id", "content"), ("content", "content")])
    n("result_message", "construct_message", arguments={"role": "tool"})
    d(*p(fi, "content"), "result_message", "content-in")
    d(*p(fi, "call_id"), "result_message", "tool-call-id-in")
    g.call("result_save", "append_history", {"history_id": p(fi, "history_id"), "message": ("result_message", "content-out")})
    g.ret("result_return", "record_tool_result")
    g.chain(fi, "result_message", "result_save", "result_return")

    # Each foreach body calls one function; branching JSON Tool logic stays inside it.
    fi = g.function("run_one_tool", [("history_id", "content"), ("call", "content"),
                                      ("batch_stop_id", "content")])
    n("call_parse", "json_to_struct", arguments={"value_type": "struct:ToolCall"})
    d(*p(fi, "call"), "call_parse", "content-in")
    g.get("call_id", "ToolCall", "id", "call_parse", "value-out")
    g.get("call_function", "ToolCall", "function", "call_parse", "value-out")
    g.get("call_name", "CallFunction", "name", "call_function", "value-out")
    g.get("call_arguments", "CallFunction", "arguments", "call_function", "value-out")
    g.ctx("batch_stop_read", "read", "content")
    d(*p(fi, "batch_stop_id"), "batch_stop_read", "context-id")
    n("batch_stop_route", "router", arguments={"branches": [{"id": "stopped", "name": "true"}]})
    d("batch_stop_read", "value-out", "batch_stop_route", "content-in")
    n("call_kind_route", "router", arguments={"branches": [{"id": "human", "name": "ask_human"}]})
    d("call_name", "value-out", "call_kind_route", "content-in")

    n("invoke_tool", "json_tool")
    d("call_name", "value-out", "invoke_tool", "tool-name")
    d("call_arguments", "value-out", "invoke_tool", "arguments-json")
    g.call("save_success", "record_tool_result", {
        "history_id": p(fi, "history_id"), "call_id": ("call_id", "value-out"),
        "content": ("invoke_tool", "result-json"),
    })
    g.call("save_error", "record_tool_result", {
        "history_id": p(fi, "history_id"), "call_id": ("call_id", "value-out"),
        "content": ("invoke_tool", "error-json"),
    })
    g.ret("tool_success_return", "run_one_tool")
    g.ret("tool_error_return", "run_one_tool")
    g.chain(fi, "call_parse", "call_id", "call_function", "call_name", "call_arguments", "batch_stop_read", "batch_stop_route")
    g.control("batch_stop_route", "stale_tool_text", "stopped")
    g.control("batch_stop_route", "call_kind_route", "branch$others")
    g.control("call_kind_route", "invoke_tool", "branch$others")
    g.chain("invoke_tool", "save_success", "tool_success_return")
    g.control("invoke_tool", "save_error", "error-out")
    g.chain("save_error", "tool_error_return")

    n("stale_tool_text", "construct_content", arguments={"append_items": [
        {"type": "fixed", "value": "Skipped because ask_human changed the plan; re-evaluate after the human reply."}
    ]}, dataInputPorts=[])
    g.call("stale_tool_message", "record_tool_result", {
        "history_id": p(fi, "history_id"), "call_id": ("call_id", "value-out"),
        "content": ("stale_tool_text", "content-out"),
    })
    g.ret("stale_tool_return", "run_one_tool")
    g.chain("stale_tool_text", "stale_tool_message", "stale_tool_return")

    # ask_human is model-visible only; it is handled by the process terminal.
    n("ask_args_parse", "json_to_struct", arguments={"value_type": "struct:AskHumanArgs"})
    d("call_arguments", "value-out", "ask_args_parse", "content-in")
    g.get("ask_question", "AskHumanArgs", "question", "ask_args_parse", "value-out")
    g.ctx("batch_stop_true", "write", "content")
    d(*p(fi, "batch_stop_id"), "batch_stop_true", "context-id")
    g.const("batch_stopped", "true")
    d("batch_stopped", "content-out", "batch_stop_true", "value-in")
    g.text("human_prompt", "The agent asks: ", "\nReply in the process terminal.")
    d("ask_question", "value-out", "human_prompt", "value")
    n("show_human_prompt", "output_to_terminal")
    d("human_prompt", "content-out", "show_human_prompt", "content-in")
    n("human_inputs_after", "read_terminal_queue")
    # Consume every pending reply in arrival order, without a history cursor.
    g.make_struct("human_reply_value", "HumanReply", {
        "replies": ("human_inputs_after", "list-out", "list-content"),
    })
    n("human_reply_json", "struct_to_json", arguments={"value_type": "struct:HumanReply"})
    d("human_reply_value", "struct-out", "human_reply_json", "value-in", "struct:HumanReply")
    g.call("save_human_reply", "record_tool_result", {
        "history_id": p(fi, "history_id"), "call_id": ("call_id", "value-out"),
        "content": ("human_reply_json", "content-out"),
    })
    g.ret("human_reply_return", "run_one_tool")
    g.control("call_kind_route", "ask_args_parse", "human")
    g.chain("ask_args_parse", "ask_question", "batch_stopped", "batch_stop_true",
            "human_prompt", "show_human_prompt", "human_inputs_after",
            "human_reply_value", "human_reply_json", "save_human_reply", "human_reply_return")

    fi = g.function("tool_loop_turn", [("history_id", "content"), ("tokens_id", "content")])
    g.ctx("read_for_llm", "read"); d(*p(fi, "history_id"), "read_for_llm", "context-id")
    n("list_files_tool", "construct_tool", arguments={
        "tool_name": "workspace.list_files", "description": "List workspace files",
        "schema": {"type": "object", "properties": {}, "additionalProperties": False},
    })
    n("get_file_tool", "construct_tool", arguments={
        "tool_name": "workspace.get_file", "description": "Read a workspace file",
        "schema": {"type": "object", "properties": {"file_id": {"type": "string", "minLength": 1}},
                   "required": ["file_id"], "additionalProperties": False},
    })
    n("ask_human_tool", "construct_tool", arguments={
        "tool_name": "ask_human", "description": "Ask the user for clarification, a decision, or missing information. Wait for new replies, returned as a replies list. Remaining calls in this batch are skipped; plan again using the reply.",
        "schema": {"type": "object", "properties": {"question": {"type": "string", "minLength": 1}},
                   "required": ["question"], "additionalProperties": False},
    })
    n("available_tools", "construct_list", arguments={"item_type": "content", "initial_value_count": 3},
      dataInputPorts=["content-in-0", "content-in-1", "content-in-2"])
    d("list_files_tool", "tool-out", "available_tools", "content-in-0")
    d("get_file_tool", "tool-out", "available_tools", "content-in-1")
    d("ask_human_tool", "tool-out", "available_tools", "content-in-2")
    n("llm", "llm", arguments={"model": "REPLACE_WITH_MODEL_ID", "think": True,
                                 "tool_calls": True, "tools_source": "definitions"})
    d("read_for_llm", "value-out", "llm", "messages-in", "list-content")
    d("available_tools", "list-out", "llm", "tools-in", "list-content")
    g.text("normalize_content"); d("llm", "output", "normalize_content", "value")
    g.call("assistant_message", "build_assistant", {
        "content": ("normalize_content", "content-out"), "reasoning": ("llm", "reasoning"),
        "calls": ("llm", "tool_calls", "list-content"),
    })
    g.call("save_assistant", "append_history", {
        "history_id": p(fi, "history_id"), "message": ("assistant_message", "function:message"),
    })
    n("turn_count", "list_length", arguments={"value_type": "list-content"})
    d("llm", "tool_calls", "turn_count", "list-in", "list-content")
    g.make_struct("turn_count_value", "ToolCallCount", {"count": ("turn_count", "length-out", "number")})
    n("turn_count_json", "struct_to_json", arguments={"value_type": "struct:ToolCallCount"})
    d("turn_count_value", "struct-out", "turn_count_json", "value-in", "struct:ToolCallCount")
    n("turn_count_text", "deserialize_json", arguments={"outputs": [{"key": "count", "type": "content"}]})
    d("turn_count_json", "content-out", "turn_count_text", "content-in")
    n("turn_route", "router", arguments={"branches": [{"id": "final", "name": "0"}]})
    d("turn_count_text", "count", "turn_route", "content-in")
    g.control(fi, "read_for_llm")
    g.chain("read_for_llm", "list_files_tool", "get_file_tool", "ask_human_tool", "available_tools", "llm",
            "normalize_content", "assistant_message", "save_assistant", "turn_count",
            "turn_count_value", "turn_count_json", "turn_count_text", "turn_route")
    n("show_final", "output_to_terminal")
    d("normalize_content", "content-out", "show_final", "content-in")
    g.ret("turn_final_return", "tool_loop_turn")
    g.control("turn_route", "show_final", "final")
    g.chain("show_final", "turn_final_return")
    n("execute_calls", "foreach", arguments={"item_type": "content"})
    d("llm", "tool_calls", "execute_calls", "list-in", "list-content")
    stop_initial = g.const("batch_stop_initial", "false")
    g.ctx("batch_stop_context", "create", "content")
    d(stop_initial, "content-out", "batch_stop_context", "initial-value")
    g.call("execute_each", "run_one_tool", {
        "history_id": p(fi, "history_id"), "call": ("execute_calls", "item-out"),
        "batch_stop_id": ("batch_stop_context", "context-id"),
    })
    g.call("queue_next_turn", "queue_turn", {"tokens_id": p(fi, "tokens_id")})
    g.ret("turn_tools_return", "tool_loop_turn")
    g.control("turn_route", "batch_stop_initial", "branch$others")
    g.chain("batch_stop_initial", "batch_stop_context", "execute_calls")
    g.control("execute_calls", "execute_each", "loop-out")
    g.control("execute_each", "execute_calls", in_port="loop-in")
    g.chain("execute_calls", "queue_next_turn", "turn_tools_return")

    return g.doc


if __name__ == "__main__":
    destination = Path(__file__).resolve().parents[1] / "docs/examples/tool-loop-agent.flow"
    destination.write_text(json.dumps(build_workflow(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(destination)
