"""Build a bootstrap whose canvas is composed of small local workflow functions."""
from restricted_workflow_graph import (
    label_functions, new_graph, output, pack, parse, result, text, tool, tool_result_json,
)

RUN_FIELDS = [("task", "content"), ("record_id", "content"), ("record_name", "content"),
              ("checkpoint_before", "number"), ("workspace_before", "content")]
OUTCOME_FIELDS = [("status", "content"), ("result", "content"), ("error", "content")]
ATTEMPT_FIELDS = OUTCOME_FIELDS + [("checkpoint_seq", "number"), ("source", "content")]
VERSION_FIELDS = [("content", "content"), ("checkpoint_seq", "number"), ("source", "content")]


def unpack(g, prefix, struct, source, fields):
    nodes, values = [], {}
    for name, kind in fields:
        node = g.get(prefix + "_" + name, struct, name, source[0], source[1])
        nodes.append(node)
        values[name] = (node, "value-out", kind)
    g.chain(*nodes)
    return nodes[0], nodes[-1], values


def _build_initialize_run(g, prefix):
    fi = g.function("initialize_run", [("task", "content")], [("run", "struct:Run")])
    begin, cp = tool(g, "checkpoint_before", "workspace.create_checkpoint", arguments={"name": prefix + ": before task"})
    inv, _ = tool(g, "inventory_before", "workspace.list_files")
    snapshot = tool_result_json(g, "inventory_before")
    parse(g, "before_seq", (cp, "output"), [("seq", "number")])
    g.node("seq_text", "number_to_content")
    g.data("before_seq", "seq", "seq_text", "number-in", "number")
    text(g, "record_name", [prefix + "-run-", ("seq_text", "content-out"), ".json"])
    running = g.const("running", "running")
    start, end = pack(g, "initial_record", {
        "status": (running, "content-out"), "task": (fi, "function:task"),
        "checkpoint_before": ("before_seq", "seq", "number"), "workspace_before": (snapshot, "content-out"),
    })
    create, created = tool(g, "create_record", "workspace.create_file", bindings={
        "name": ("record_name", "content-out"), "content": (end, "content-out"),
    })
    parse(g, "record_file", (created, "output"), [("file_id", "content")])
    g.make_struct("run_info", "Run", {
        "task": (fi, "function:task", "content"), "record_id": ("record_file", "file_id", "content"),
        "record_name": ("record_name", "content-out", "content"),
        "checkpoint_before": ("before_seq", "seq", "number"), "workspace_before": (snapshot, "content-out", "content"),
    })
    ret = result(g, "initialize_return", "initialize_run", {"run": ("run_info", "struct-out", "struct:Run")})
    g.chain(fi, begin)
    g.control(cp, inv)
    g.chain(snapshot, "before_seq", "seq_text", "record_name", running, start)
    g.control(end, create)
    g.chain(created, "record_file", "run_info", ret)


def _build_write_record(g):
    fi = g.function("write_record", [("record_id", "content"), ("record_name", "content"), ("content", "content")])
    read, read_end = tool(g, "read_record", "workspace.get_file", bindings={"file_id": (fi, "function:record_id")})
    parse(g, "record_revision", (read_end, "output"), [("revision", "number")])
    write, write_end = tool(g, "write_record_file", "workspace.update_file", bindings={
        "file_id": (fi, "function:record_id"), "name": (fi, "function:record_name"),
        "content": (fi, "function:content"), "revision": ("record_revision", "revision", "number"),
    })
    g.ret("write_record_return", "write_record")
    g.chain(fi, read)
    g.chain(read_end, "record_revision", write)
    g.control(write_end, "write_record_return")


def _build_attempt_main(g, prefix):
    fi = g.function("attempt_main", [("task", "content"), ("checkpoint_seq", "number"),
                                    ("source", "content"), ("success_status", "content")], [("attempt", "struct:Attempt")])
    main = g.const("main_name", prefix + "-main.flow")
    start, end = pack(g, "main_arguments", {"task": (fi, "function:task")})
    g.node("call_main", "spawn_and_wait_subprocess")
    g.data(main, "content-out", "call_main", "workflow-file")
    g.data(end, "content-out", "call_main", "arguments-json")
    g.chain(fi, main, start)
    g.control(end, "call_main")
    for suffix, port, control in (("ok", "result-json", "control-out"), ("error", "error-json", "error-out")):
        first = g.const("attempt_" + suffix + "_value", "" if suffix == "ok" else "failed")
        g.make_struct("attempt_" + suffix, "Attempt", {
            "status": (fi, "function:success_status", "content") if suffix == "ok" else (first, "content-out", "content"),
            "result": ("call_main", port, "content"),
            "error": (first, "content-out", "content") if suffix == "ok" else ("call_main", port, "content"),
            "checkpoint_seq": (fi, "function:checkpoint_seq", "number"), "source": (fi, "function:source", "content"),
        })
        ret = result(g, "attempt_" + suffix + "_return", "attempt_main", {"attempt": ("attempt_" + suffix, "struct-out", "struct:Attempt")})
        g.control("call_main", first, control)
        g.chain(first, "attempt_" + suffix, ret)


def _build_remember_attempt(g):
    fi = g.function("remember_attempt", [("run", "struct:Run"), ("attempt", "struct:Attempt"),
                                         ("state_id", "content"), ("attempts_id", "content")])
    run_start, run_end, run = unpack(g, "remember_run", "Run", (fi, "function:run"), RUN_FIELDS)
    attempt_start, attempt_end, attempt = unpack(g, "remember_attempt", "Attempt", (fi, "function:attempt"), ATTEMPT_FIELDS)
    g.node("attempt_json", "struct_to_json", arguments={"value_type": "struct:Attempt"})
    g.data(fi, "function:attempt", "attempt_json", "value-in", "struct:Attempt")
    g.ctx("attempts_read", "read")
    g.data(fi, "function:attempts_id", "attempts_read", "context-id")
    g.node("append_attempt", "list_append", arguments={"item_type": "content", "position": "end"})
    g.data("attempts_read", "value-out", "append_attempt", "list-in", "list-content")
    g.data("attempt_json", "content-out", "append_attempt", "item-in")
    g.ctx("attempts_write", "write")
    g.data(fi, "function:attempts_id", "attempts_write", "context-id")
    g.data("append_attempt", "list-out", "attempts_write", "value-in", "list-content")
    g.ctx("state_read", "read", "struct:Outcome")
    g.data(fi, "function:state_id", "state_read", "context-id")
    g.get("prior_errors", "Outcome", "error", "state_read", "value-out")
    text(g, "all_errors", [("prior_errors", "value-out"), "\n", attempt["error"][:2]])
    g.make_struct("updated_outcome", "Outcome", {
        "status": attempt["status"], "result": attempt["result"], "error": ("all_errors", "content-out", "content"),
    })
    g.ctx("state_write", "write", "struct:Outcome")
    g.data(fi, "function:state_id", "state_write", "context-id")
    g.data("updated_outcome", "struct-out", "state_write", "value-in", "struct:Outcome")
    start, end = pack(g, "progress_record", {
        "task": run["task"], "status": attempt["status"], "result": attempt["result"],
        "error": ("all_errors", "content-out"), "checkpoint_before": run["checkpoint_before"],
        "workspace_before": run["workspace_before"], "attempts": ("append_attempt", "list-out", "list-content"),
    })
    g.call("save_progress", "write_record", {"record_id": run["record_id"], "record_name": run["record_name"], "content": (end, "content-out")})
    g.ret("remember_return", "remember_attempt")
    g.chain(fi, run_start)
    g.chain(run_end, attempt_start)
    g.chain(attempt_end, "attempt_json", "attempts_read", "append_attempt", "attempts_write", "state_read",
            "prior_errors", "all_errors", "updated_outcome", "state_write", start)
    g.chain(end, "save_progress", "remember_return")


def _build_restore_version(g, main_id):
    fi = g.function("restore_main_version", [("content", "content")])
    read, read_end = tool(g, "read_main", "workspace.get_file", arguments={"file_id": main_id})
    parse(g, "main_file", (read_end, "output"), [("name", "content"), ("revision", "number")])
    target = g.const("restore_main_id", main_id)
    restore, restored = tool(g, "restore_main", "workspace.update_file", bindings={
        "file_id": (target, "content-out"), "name": ("main_file", "name"),
        "content": (fi, "function:content"), "revision": ("main_file", "revision", "number"),
    })
    g.ret("restore_return", "restore_main_version")
    g.chain(fi, read)
    g.chain(read_end, "main_file", target, restore)
    g.control(restored, "restore_return")


def _build_retry_version(g):
    fi = g.function("retry_version", [("run", "struct:Run"), ("version", "struct:RecoveryVersion"),
                                     ("state_id", "content"), ("attempts_id", "content"), ("versions_id", "content")])
    rs, re, run = unpack(g, "retry_run", "Run", (fi, "function:run"), [("task", "content")])
    vs, ve, version = unpack(g, "retry_version", "RecoveryVersion", (fi, "function:version"), VERSION_FIELDS)
    g.call("restore_candidate", "restore_main_version", {"content": version["content"]})
    recovered = g.const("recovered_status", "recovered")
    g.call("retry_main", "attempt_main", {"task": run["task"], "checkpoint_seq": version["checkpoint_seq"],
                                          "source": version["source"], "success_status": (recovered, "content-out")})
    g.call("remember_retry", "remember_attempt", {"run": (fi, "function:run", "struct:Run"),
        "attempt": ("retry_main", "function:attempt", "struct:Attempt"),
        "state_id": (fi, "function:state_id"), "attempts_id": (fi, "function:attempts_id")})
    g.get("retry_status", "Attempt", "status", "retry_main", "function:attempt")
    g.node("retry_route", "router", arguments={"branches": [{"id": "success", "name": "recovered"}]})
    g.data("retry_status", "value-out", "retry_route", "content-in")
    empty = g.const("empty_recovery_json", "[]")
    g.node("empty_recovery", "json_to_struct", arguments={"value_type": "list-struct:RecoveryVersion"})
    g.data(empty, "content-out", "empty_recovery", "content-in")
    g.ctx("stop_recovery", "write", "list-struct:RecoveryVersion")
    g.data(fi, "function:versions_id", "stop_recovery", "context-id")
    g.data("empty_recovery", "value-out", "stop_recovery", "value-in", "list-struct:RecoveryVersion")
    g.ret("retry_success_return", "retry_version")
    g.ret("retry_failed_return", "retry_version")
    g.chain(fi, rs)
    g.chain(re, vs)
    g.chain(ve, "restore_candidate", recovered, "retry_main", "remember_retry", "retry_status", "retry_route")
    g.control("retry_route", empty, "success")
    g.chain(empty, "empty_recovery", "stop_recovery", "retry_success_return")
    g.control("retry_route", "retry_failed_return", "branch$others")


def _recovery_return(g, prefix):
    g.ctx(prefix + "_state", "read", "struct:Outcome")
    g.data("outcome_context", "context-id", prefix + "_state", "context-id")
    g.ctx(prefix + "_attempts", "read")
    g.data("attempts_context", "context-id", prefix + "_attempts", "context-id")
    ret = result(g, prefix + "_return", "run_with_recovery", {
        "outcome": (prefix + "_state", "value-out", "struct:Outcome"),
        "attempts": (prefix + "_attempts", "value-out", "list-content"),
    })
    g.chain(prefix + "_state", prefix + "_attempts", ret)
    return prefix + "_state"


def _build_run_with_recovery(g, main_id, stable_id):
    fi = g.function("run_with_recovery", [("run", "struct:Run")], [("outcome", "struct:Outcome"), ("attempts", "list-content")])
    rs, re, run = unpack(g, "execution_run", "Run", (fi, "function:run"), [("task", "content"), ("checkpoint_before", "number")])
    g.node("empty_attempts", "construct_list", arguments={"item_type": "content", "initial_value_count": 0}, dataInputPorts=[])
    g.ctx("attempts_context", "create")
    g.data("empty_attempts", "list-out", "attempts_context", "initial-value", "list-content")
    failed = g.const("default_status", "failed")
    empty = g.const("default_text", "")
    g.make_struct("default_outcome", "Outcome", {"status": (failed, "content-out", "content"),
                                               "result": (empty, "content-out", "content"), "error": (empty, "content-out", "content")})
    g.ctx("outcome_context", "create", "struct:Outcome")
    g.data("default_outcome", "struct-out", "outcome_context", "initial-value", "struct:Outcome")
    source = g.const("current_source", "current")
    completed = g.const("completed_status", "completed")
    g.call("first_attempt", "attempt_main", {"task": run["task"], "checkpoint_seq": run["checkpoint_before"],
                                            "source": (source, "content-out"), "success_status": (completed, "content-out")})
    g.call("remember_first", "remember_attempt", {"run": (fi, "function:run", "struct:Run"),
        "attempt": ("first_attempt", "function:attempt", "struct:Attempt"),
        "state_id": ("outcome_context", "context-id"), "attempts_id": ("attempts_context", "context-id")})
    g.get("first_status", "Attempt", "status", "first_attempt", "function:attempt")
    g.node("first_route", "router", arguments={"branches": [{"id": "success", "name": "completed"}]})
    g.data("first_status", "value-out", "first_route", "content-in")
    plan, plan_end = tool(g, "recovery_plan", "workspace.get_file_recovery_plan", bindings={"checkpoint_seq": run["checkpoint_before"]},
                          arguments={"file_id": main_id, "stable_file_id": stable_id})
    g.node("recovery_versions", "json_to_struct", arguments={"value_type": "list-struct:RecoveryVersion"})
    g.data(plan_end, "versions", "recovery_versions", "content-in")
    g.ctx("versions_context", "create", "list-struct:RecoveryVersion")
    g.data("recovery_versions", "value-out", "versions_context", "initial-value", "list-struct:RecoveryVersion")
    g.node("recovery_gate", "while_pop", arguments={"value_type": "list-struct:RecoveryVersion", "position": "start"})
    g.data("versions_context", "context-id", "recovery_gate", "context-id")
    g.call("recover_one", "retry_version", {"run": (fi, "function:run", "struct:Run"),
        "version": ("recovery_gate", "item-out", "struct:RecoveryVersion"), "state_id": ("outcome_context", "context-id"),
        "attempts_id": ("attempts_context", "context-id"), "versions_id": ("versions_context", "context-id")})
    done = _recovery_return(g, "first_success")
    exhausted = _recovery_return(g, "recovery_done")
    g.chain(fi, rs)
    g.chain(re, "empty_attempts", "attempts_context", failed, empty, "default_outcome", "outcome_context",
            source, completed, "first_attempt", "remember_first", "first_status", "first_route")
    g.control("first_route", done, "success")
    g.control("first_route", plan, "branch$others")
    g.chain(plan_end, "recovery_versions", "versions_context", "recovery_gate")
    g.control("recovery_gate", "recover_one", "loop-out")
    g.control("recover_one", "recovery_gate", in_port="loop-in")
    g.control("recovery_gate", exhausted)


def _build_call_iterator(g, prefix):
    fi = g.function("call_iterator", [("record", "content")], [("status", "content"), ("result", "content")])
    name = g.const("iterator_name", prefix + "-iterator.flow")
    start, end = pack(g, "iterator_arguments", {"record": (fi, "function:record")})
    g.node("invoke_iterator", "spawn_and_wait_subprocess")
    g.data(name, "content-out", "invoke_iterator", "workflow-file")
    g.data(end, "content-out", "invoke_iterator", "arguments-json")
    g.chain(fi, name, start)
    g.control(end, "invoke_iterator")
    for suffix, status, port, control in (("ok", "completed", "result-json", "control-out"), ("error", "failed", "error-json", "error-out")):
        flag = g.const("iterator_" + suffix, status)
        ret = result(g, "iterator_" + suffix + "_return", "call_iterator", {"status": (flag, "content-out"), "result": ("invoke_iterator", port)})
        g.control("invoke_iterator", flag, control)
        g.control(flag, ret)


def _build_finish_task(g, prefix, terminal_summary=True):
    fi = g.function("finish_task", [("run", "struct:Run"), ("outcome", "struct:Outcome"), ("attempts", "list-content")],
                    [("status", "content"), ("result", "content"), ("record_file_id", "content")])
    rs, re, run = unpack(g, "finish_run", "Run", (fi, "function:run"), RUN_FIELDS)
    os, oe, outcome = unpack(g, "finish_outcome", "Outcome", (fi, "function:outcome"), OUTCOME_FIELDS)
    after, after_end = tool(g, "checkpoint_after", "workspace.create_checkpoint", arguments={"name": prefix + ": after task"})
    inv, _ = tool(g, "inventory_after", "workspace.list_files")
    snapshot = tool_result_json(g, "inventory_after")
    parse(g, "after_seq", (after_end, "output"), [("seq", "number")])
    changes, _ = tool(g, "workspace_changes", "workspace.checkpoint_diff", bindings={"seq": ("after_seq", "seq", "number")})
    changes_json = tool_result_json(g, "workspace_changes")
    start, end = pack(g, "task_record", {**outcome, "task": run["task"], "checkpoint_before": run["checkpoint_before"],
        "workspace_before": run["workspace_before"], "checkpoint_after": ("after_seq", "seq", "number"),
        "workspace_after": (snapshot, "content-out"), "workspace_changes": (changes_json, "content-out"),
        "attempts": (fi, "function:attempts", "list-content")})
    record = {"record_id": run["record_id"], "record_name": run["record_name"]}
    g.call("save_task_record", "write_record", {**record, "content": (end, "content-out")})
    g.call("iterate_experience", "call_iterator", {"record": (end, "content-out")})
    final_start, final_end = pack(g, "completed_record", {"task_record": (end, "content-out"),
        "iterator_status": ("iterate_experience", "function:status"), "iterator_result": ("iterate_experience", "function:result")})
    g.call("save_final_record", "write_record", {**record, "content": (final_end, "content-out")})
    cp, cp_end = tool(g, "checkpoint_final", "workspace.create_checkpoint", arguments={"name": prefix + ": after iterator"})
    if terminal_summary:
        text(g, "summary", ["任务状态：", outcome["status"][:2], "\n结果：", outcome["result"][:2],
            "\n迭代器状态：", ("iterate_experience", "function:status"), "\n记录文件：", run["record_id"][:2]])
        g.node("show_summary", "output_to_terminal")
        g.data("summary", "content-out", "show_summary", "content-in")
    ret = result(g, "finish_return", "finish_task", {"status": outcome["status"], "result": outcome["result"], "record_file_id": run["record_id"]})
    g.chain(fi, rs)
    g.chain(re, os)
    g.chain(oe, after)
    g.control(after_end, inv)
    g.chain(snapshot, "after_seq", changes)
    g.control(changes_json, start)
    g.chain(end, "save_task_record", "iterate_experience", final_start)
    g.chain(final_end, "save_final_record", cp)
    if terminal_summary:
        g.chain(cp_end, "summary", "show_summary", ret)
    else:
        g.control(cp_end, ret)


def build_bootstrap(main_id, stable_id, prefix="restricted-agent"):
    g = new_graph("固定引导：记录任务；失败后逐级回退主流程重试，到 stable 为止；记录结果并更新经验。",
                  [("task", "content")], [("status", "content"), ("result", "content"), ("record_file_id", "content")])
    for name, fields in (("Run", RUN_FIELDS), ("Outcome", OUTCOME_FIELDS), ("Attempt", ATTEMPT_FIELDS), ("RecoveryVersion", VERSION_FIELDS)):
        g.struct(name, fields)
    g.call("initialize", "initialize_run", {"task": ("in", "workflow:task")})
    g.call("execute", "run_with_recovery", {"run": ("initialize", "function:run", "struct:Run")})
    g.call("finish", "finish_task", {"run": ("initialize", "function:run", "struct:Run"),
        "outcome": ("execute", "function:outcome", "struct:Outcome"), "attempts": ("execute", "function:attempts", "list-content")})
    output(g)
    for field in ("status", "result", "record_file_id"):
        g.data("finish", "function:" + field, "out", "workflow:" + field)
    g.chain("in", "initialize", "execute", "finish", "out")
    add_bootstrap_functions(g, main_id, stable_id, prefix)
    return g.doc


def add_bootstrap_functions(g, main_id, stable_id, prefix, *, terminal_summary=True):
    """Shared recording, child calls and bounded file-version recovery functions."""
    _build_initialize_run(g, prefix)
    _build_run_with_recovery(g, main_id, stable_id)
    _build_attempt_main(g, prefix)
    _build_remember_attempt(g)
    _build_restore_version(g, main_id)
    _build_retry_version(g)
    _build_write_record(g)
    _build_finish_task(g, prefix, terminal_summary)
    _build_call_iterator(g, prefix)
    label_functions(g, {
        "initialize_run": "初始化任务记录", "run_with_recovery": "执行主流程与逐级恢复",
        "attempt_main": "尝试一次主流程", "remember_attempt": "保存本次尝试",
        "restore_main_version": "回退主流程版本", "retry_version": "尝试回退版本",
        "write_record": "写入任务记录", "finish_task": "记录结果并迭代经验", "call_iterator": "调用经验迭代器",
    })
