"""Small graph builders shared by the restricted workflow generators."""
import copy
import json

from build_tool_loop_workflow import Graph, ports


def encode(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def new_graph(description, inputs, outputs):
    g = Graph()
    g.doc.update(description=description, input_ports=ports(inputs), output_ports=ports(outputs))
    g.doc["metadata"]["tools"] = []
    g.node("in", "input", workflowPorts=[{"id": "workflow:" + name, "name": name, "type": kind} for name, kind in inputs])
    return g


def output(g, node_id="out"):
    return g.node(node_id, "output", workflowPorts=[{"id": "workflow:" + p["name"], **p} for p in g.doc["output_ports"]])


def text(g, node_id, parts):
    items = []
    bindings = []
    for i, part in enumerate(parts):
        if isinstance(part, str):
            items.append({"type": "fixed", "value": part})
        else:
            name = "part_" + str(i)
            items.append({"type": "port", "port_id": name})
            bindings.append((name, part))
    g.node(node_id, "construct_content", arguments={"append_items": items}, dataInputPorts=[name for name, _ in bindings])
    for name, source in bindings:
        g.data(*source, node_id, name)
    return node_id


def pack(g, node_id, bindings):
    """Construct typed JSON; interpolating raw task/model text cannot break JSON."""
    sid = node_id + "_fields"
    g.struct(sid, [(name, source[2] if len(source) > 2 else "content") for name, source in bindings.items()])
    g.make_struct(node_id + "_value", sid, {
        name: (*source[:2], source[2] if len(source) > 2 else "content") for name, source in bindings.items()
    })
    g.node(node_id, "struct_to_json", arguments={"value_type": "struct:" + sid})
    g.data(node_id + "_value", "struct-out", node_id, "value-in", "struct:" + sid)
    g.control(node_id + "_value", node_id)
    return node_id + "_value", node_id


# Array outputs use content snapshots to retain JSON objects; list-content
# requires string items and is unsuitable for these file/change records.
FIXED_TOOLS = {
    "workspace.get_file_recovery_plan": ([("file_id", "content"), ("stable_file_id", "content"),
                                          ("checkpoint_seq", "number")], [("versions", "content")]),
    "workspace.get_file": ([("file_id", "content")], [("output", "content")]),
    "workspace.create_file": ([("name", "content"), ("content", "content")], [("output", "content")]),
    "workspace.update_file": ([("file_id", "content"), ("name", "content"), ("content", "content"),
                               ("revision", "number")], [("output", "content")]),
    "workspace.create_checkpoint": ([("name", "content")], [("output", "content")]),
    "workspace.list_files": ([], [("items", "content"), ("revision", "number")]),
    "workspace.checkpoint_diff": ([("seq", "number")], [("seq", "number"), ("parent_seq", "content"),
                                                        ("changes", "content")]),
}


def tool(g, node_id, name, bindings=None, arguments=None):
    """Bind a fixed local Tool and connect its typed arguments directly."""
    parameters, outputs = (ports(items) for items in FIXED_TOOLS[name])
    declaration = {"name": name, "kind": "local", "input_ports": parameters, "output_ports": outputs}
    if declaration not in g.doc["metadata"]["tools"]:
        g.doc["metadata"]["tools"].append(copy.deepcopy(declaration))
    bindings = dict(bindings or {})
    constants = []
    for parameter, value in (arguments or {}).items():
        constants.append(g.const(node_id + "_" + parameter, value))
        bindings[parameter] = (constants[-1], "content-out")
    g.node(node_id, "tool", arguments={"tool": name, "parameters": parameters, "outputs": outputs})
    for parameter, source in bindings.items():
        g.data(*source[:2], node_id, parameter, source[2] if len(source) > 2 else "content")
    g.chain(*constants, node_id)
    return (constants[0] if constants else node_id), node_id


def tool_result_json(g, node_id):
    """Retain the record's JSON snapshots from native named Tool outputs.

    These tools expose numbers and serialized arrays/null, so every value is
    already a JSON fragment. Task/model text never enters this assembly.
    """
    node = next(node for node in g.doc["nodes"] if node["id"] == node_id)
    conversions = []
    parts = ["{"]
    for i, field in enumerate(node["arguments"]["outputs"]):
        parts.append(("," if i else "") + encode(field["name"]) + ":")
        if field["type"] == "number":
            converted = g.node(node_id + "_" + field["name"] + "_text", "number_to_content")
            g.data(node_id, field["name"], converted, "number-in", "number")
            conversions.append(converted)
            parts.append((converted, "content-out"))
        else:
            parts.append((node_id, field["name"]))
    parts.append("}")
    result = text(g, node_id + "_json", parts)
    g.chain(node_id, *conversions, result)
    return result


def parse(g, node_id, source, fields):
    g.node(node_id, "deserialize_json", arguments={"outputs": [{"key": key, "type": kind} for key, kind in fields]})
    g.data(*source, node_id, "content-in")
    return node_id


def messages(g, prefix, system_parts, user_parts):
    text(g, prefix + "_system_text", system_parts)
    g.node(prefix + "_system", "construct_message", arguments={"role": "system"})
    g.data(prefix + "_system_text", "content-out", prefix + "_system", "content-in")
    text(g, prefix + "_user_text", user_parts)
    g.node(prefix + "_user", "construct_message", arguments={"role": "user"})
    g.data(prefix + "_user_text", "content-out", prefix + "_user", "content-in")
    g.node(prefix + "_messages", "construct_list", arguments={"item_type": "content", "initial_value_count": 2},
           dataInputPorts=["content-in-0", "content-in-1"])
    g.data(prefix + "_system", "content-out", prefix + "_messages", "content-in-0")
    g.data(prefix + "_user", "content-out", prefix + "_messages", "content-in-1")
    g.chain(prefix + "_system_text", prefix + "_system", prefix + "_user_text", prefix + "_user", prefix + "_messages")
    return prefix + "_system_text", prefix + "_messages"


def result(g, node_id, function, bindings):
    g.ret(node_id, function)
    for name, source in bindings.items():
        g.data(*source[:2], node_id, "function:" + name, source[2] if len(source) > 2 else "content")
    return node_id


def label_functions(g, labels):
    """Use readable canvas names while keeping stable IDs for connections."""
    for function in g.doc["metadata"]["functions"]:
        function["name"] = labels.get(function["id"], function["name"])
    for node in g.doc["nodes"]:
        fid = node.get("function_id") if node["type"] in ("function_input", "function_output") else node.get("arguments", {}).get("function_id")
        if fid in labels:
            suffix = " / 输入" if node["type"] == "function_input" else " / 返回" if node["type"] == "function_output" else ""
            node["name"] = labels[fid] + suffix
