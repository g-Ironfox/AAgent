"""Lifecycle visibility tests shared verbatim by the two backend services."""

import copy
import unittest

from workflow_validator import WorkflowValidationError, validate_workflow


def node(node_id, kind="construct_content", **extra):
    result = {"id": node_id, "type": kind}
    if kind == "construct_content":
        result.update(dataInputPorts=["value"], arguments={"append_items": [{"type": "port", "port_id": "value"}]})
    elif kind == "router":
        result["arguments"] = {"branches": [{"id": "a", "name": "A"}]}
    elif kind == "foreach":
        result["arguments"] = {"item_type": "content"}
    result.update(extra)
    return result


def control(source, target, output="control-out", input_port="control-in"):
    return {"fromId": source, "fromPortId": output, "toId": target, "toPortId": input_port, "type": "control"}


def data(source, target, output="content-out", input_port="value", kind="content"):
    return {"fromId": source, "fromPortId": output, "toId": target, "toPortId": input_port, "type": kind}


def workflow(nodes, connections):
    inputs = [{"name": "value", "type": "content"}, {"name": "items", "type": "list-content"}]
    outputs = [{"name": "value", "type": "content"}]
    for item in nodes:
        if item["type"] in {"input", "output"}:
            ports = inputs if item["type"] == "input" else outputs
            item["workflowPorts"] = [{"id": "workflow:" + port["name"], **port} for port in ports]
    return {"schema_version": "2.0", "name": "lifecycle", "input_ports": inputs,
            "output_ports": outputs, "nodes": nodes, "connections": connections}


def branches():
    return workflow(
        [node("i", "input"), node("r", "router"), node("a"), node("b"), node("oa", "output"), node("ob", "output")],
        [control("i", "r"), control("r", "a", "a"), control("r", "b", "branch$others"),
         control("a", "oa"), control("b", "ob"), data("i", "r", "workflow:value", "content-in")],
    )


def loop():
    return workflow(
        [node("i", "input"), node("f", "foreach"), node("body"), node("o", "output")],
        [control("i", "f"), control("f", "body", "loop-out"), control("body", "f", input_port="loop-in"),
         control("f", "o"), data("i", "f", "workflow:items", "list-in", "list-content")],
    )


def test_cases():
    """Also consumed by the editor parity test, using actual protocol documents."""
    cases = []
    def add(name, graph, error=None):
        cases.append({"name": name, "workflow": graph, "error": error})

    g = branches()
    g["connections"] += [data("i", "a", "workflow:value"), data("i", "b", "workflow:value"), data("a", "oa", input_port="workflow:value")]
    add("parent inputs and same-scope values", g)

    g = branches()
    g["connections"].append(data("a", "b"))
    add("sibling branches", g, "crosses lifecycle boundary")
    g = branches()
    g["connections"].append(data("b", "a"))
    add("fallback to regular branch", g, "crosses lifecycle boundary")
    g = branches()
    g["connections"].append(data("a", "r", input_port="content-in"))
    g["connections"] = [edge for edge in g["connections"] if not (edge["fromId"] == "i" and edge["type"] == "content")]
    add("branch to parent boundary input", g, "crosses lifecycle boundary")

    g = branches()
    g["nodes"] = [item for item in g["nodes"] if item["id"] != "ob"]
    next(edge for edge in g["connections"] if edge["fromId"] == "b")["toId"] = "oa"
    add("branches may not merge at Output", g, "control-flow merge")

    g = branches()
    g["nodes"] += [node("r2", "router"), node("oc", "output", workflowPorts=[{"id": "workflow:value", "name": "value", "type": "content"}])]
    next(edge for edge in g["connections"] if edge["fromId"] == "a")["toId"] = "r2"
    g["connections"] += [control("r2", "oa", "a"), control("r2", "oc", "branch$others"), data("a", "r2", input_port="content-in"), data("a", "oa", input_port="workflow:value")]
    add("nested branch inherits ancestor", g)
    bad = copy.deepcopy(g)
    bad["connections"].append(data("b", "oc", input_port="workflow:value"))
    add("nested branch cannot read its cousin", bad, "crosses lifecycle boundary")

    g = loop()
    g["connections"] += [data("f", "body", "item-out"), data("i", "o", "workflow:value", "workflow:value")]
    add("foreach input body and continuation scopes", g)
    g = loop()
    g["connections"].append(data("body", "o", input_port="workflow:value"))
    add("loop body leak", g, "crosses lifecycle boundary")
    g = loop()
    g["connections"].append(data("f", "o", "item-out", "workflow:value"))
    add("foreach item-out leak", g, "crosses lifecycle boundary")

    g = loop()
    g["nodes"] = [item for item in g["nodes"] if item["id"] != "body"]
    g["connections"] = [control("i", "f"), control("f", "f", "loop-out", "loop-in"), control("f", "o")]
    add("empty body self return", g)

    g = branches()
    g["nodes"][2] = node("a", "foreach")
    g["nodes"].append(node("body"))
    g["connections"] += [control("a", "body", "loop-out"), control("body", "a", input_port="loop-in"), data("i", "a", "workflow:items", "list-in", "list-content"), data("a", "body", "item-out")]
    add("foreach within a router branch", g)
    bad = copy.deepcopy(g)
    bad["connections"].append(data("body", "b"))
    add("loop body cannot leak to another branch", bad, "crosses lifecycle boundary")

    g = loop()
    g["nodes"] += [node("g", "foreach"), node("body2")]
    next(edge for edge in g["connections"] if edge["fromId"] == "f" and edge["fromPortId"] == "control-out")["toId"] = "g"
    g["connections"] += [control("g", "body2", "loop-out"), control("body2", "g", input_port="loop-in"), control("g", "o")]
    add("sequential loops", g)
    bad = copy.deepcopy(g)
    bad["connections"].append(data("body", "body2"))
    add("sequential loops cannot exchange local values", bad, "crosses lifecycle boundary")

    g = loop()
    g["nodes"][2] = node("body", "context_write", arguments={"value_type": "content", "context_id_source": "fixed", "context_id": "accumulator"})
    g["nodes"].append(node("read", "context_read", arguments={"value_type": "content", "context_id_source": "fixed", "context_id": "accumulator"}))
    next(edge for edge in g["connections"] if edge["fromId"] == "f" and edge["fromPortId"] == "control-out")["toId"] = "read"
    g["connections"] += [data("f", "body", "item-out", "value-in"), control("read", "o"), data("read", "o", "value-out", "workflow:value")]
    add("Context explicitly exports a loop result", g)
    bad = copy.deepcopy(g)
    bad["connections"] = [edge for edge in bad["connections"] if edge["fromId"] != "read" or edge["type"] == "control"]
    bad["connections"].append(data("body", "o", "value-out", "workflow:value"))
    add("Context write output is still loop local", bad, "crosses lifecycle boundary")

    g = branches()
    g["nodes"][1] = node("r", "json_tool")
    next(edge for edge in g["connections"] if edge["fromId"] == "r" and edge["fromPortId"] == "a")["fromPortId"] = "control-out"
    next(edge for edge in g["connections"] if edge["fromId"] == "r" and edge["fromPortId"] == "branch$others")["fromPortId"] = "error-out"
    next(edge for edge in g["connections"] if edge["toId"] == "r" and edge["type"] == "content")["toPortId"] = "tool-name"
    g["connections"] += [data("r", "a", "result-json"), data("r", "b", "error-json")]
    add("JSON Tool success and error boundaries", g)
    bad = copy.deepcopy(g)
    bad["connections"] = [edge for edge in bad["connections"] if edge["fromPortId"] != "error-json"]
    bad["connections"].append(data("r", "b", "result-json"))
    add("JSON Tool result cannot enter error branch", bad, "crosses lifecycle boundary")
    g = workflow([node("i", "input"), node("j", "json_tool"), node("o", "output")], [control("i", "j"), control("j", "o"), data("j", "o", "result-json", "workflow:value")])
    add("JSON Tool optional error branch", g)

    g = branches()
    next(edge for edge in g["connections"] if edge["fromId"] == "a")["toId"] = "b"
    next(edge for edge in g["connections"] if edge["fromId"] == "b")["toId"] = "a"
    g["nodes"] = [item for item in g["nodes"] if item["id"] not in {"oa", "ob"}]
    g["nodes"].append(node("oa", "output", workflowPorts=[{"id": "workflow:value", "name": "value", "type": "content"}]))
    next(edge for edge in g["connections"] if edge["fromPortId"] == "branch$others")["toId"] = "oa"
    add("non-foreach cycle", g, "control-flow cycle")
    g = loop()
    next(edge for edge in g["connections"] if edge["fromId"] == "i" and edge["type"] == "control")["toPortId"] = "loop-in"
    add("outside entry into loop-in", g, "control ports must be connected")
    g = loop()
    g["nodes"][2] = node("body", "router", arguments={"branches": []})
    next(edge for edge in g["connections"] if edge["fromId"] == "body")["fromPortId"] = "branch$others"
    add("even fallback-only router is forbidden in foreach", g, "branching control flow")
    g = workflow(
        [node("i", "input"), node("o", "output"), node("island")],
        [control("i", "o"), control("island", "island")],
    )
    add("disconnected cycle with connected ports", g, "unreachable from input")
    g = branches()
    g["nodes"].append(node("island"))
    g["connections"].append(control("island", "island"))
    add("unreachable node alongside valid branches", g, "unreachable from input")
    g = loop()
    g["nodes"][2] = node("body", "foreach")
    g["nodes"].append(node("nested"))
    g["connections"] += [control("body", "nested", "loop-out"), control("nested", "body", input_port="loop-in")]
    add("nested foreach follows existing no-branch restriction", g, "branching control flow")
    return cases


class WorkflowLifecyclesTest(unittest.TestCase):
    def test_protocol_documents(self):
        for case in test_cases():
            with self.subTest(case=case["name"]):
                before = copy.deepcopy(case["workflow"])
                if case["error"]:
                    with self.assertRaisesRegex(WorkflowValidationError, case["error"]):
                        validate_workflow(case["workflow"])
                else:
                    validate_workflow(case["workflow"])
                    validate_workflow(case["workflow"])
                self.assertEqual(case["workflow"], before)


if __name__ == "__main__":
    unittest.main()
