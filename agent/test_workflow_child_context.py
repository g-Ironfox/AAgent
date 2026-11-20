"""Execute real nested workflows against an in-memory Context store."""

import copy
import json
import unittest
from unittest.mock import MagicMock, patch

from workflow_context_repository import WorkflowContextError
from test_support import run_scheduled_workflow, json_subprocess_fixture
from workflow_nodes import propagate_workflow_output
from workflow_parser import parse_workflow
from workflow_validator import validate_workflow


INPUTS = [{"name": "context_id", "type": "content"}, {"name": "items", "type": "list-content"}]
OUTPUTS = [{"name": "items", "type": "list-content"}]


def node(node_id, kind, **arguments):
    return {"id": node_id, "type": kind, "arguments": arguments}


def data(source, output, target, input_port, kind):
    return {"fromId": source, "fromPortId": output, "toId": target, "toPortId": input_port, "type": kind}


def control(source, target, output="control-out", input_port="control-in"):
    return data(source, output, target, input_port, "control")


def call_node(name):
    return {**node("call", "spawn_and_wait_subprocess", workflow_file=name), "input_ports": INPUTS, "output_ports": OUTPUTS}


def graph(name, body, connections):
    return json_subprocess_fixture({
        "schema_version": "2.0", "name": name, "input_ports": INPUTS, "output_ports": OUTPUTS,
        "nodes": [
            {"id": "input", "type": "input", "workflowPorts": [{"id": "workflow:" + p["name"], **p} for p in INPUTS]},
            *body,
            {"id": "output", "type": "output", "workflowPorts": [{"id": "workflow:" + p["name"], **p} for p in OUTPUTS]},
        ],
        "connections": connections,
    })


def wrapper(name, child):
    return graph(name, [call_node(child)], [
        control("input", "call"), control("call", "output"),
        data("input", "workflow:context_id", "call", "workflow:context_id", "content"),
        data("input", "workflow:items", "call", "workflow:items", "list-content"),
        data("call", "workflow:items", "output", "workflow:items", "list-content"),
    ])


def leaf(pop_position=None, fail=False):
    body = [node("read", "context_read", value_type="list-content")]
    edges = [control("input", "read"), data("input", "workflow:context_id", "read", "context-id", "content")]
    if pop_position is None:
        body += [node("item", "construct_content", append_items=[{"type": "fixed", "value": "child"}]),
                 node("append", "list_append", item_type="content", position="end"),
                 node("write", "context_write", value_type="list-content")]
        edges += [control("read", "item"), control("item", "append"), control("append", "write"),
                  data("read", "value-out", "append", "list-in", "list-content"),
                  data("item", "content-out", "append", "item-in", "content"),
                  data("input", "workflow:context_id", "write", "context-id", "content"),
                  data("append", "list-out", "write", "value-in", "list-content")]
        previous = "write"
    else:
        body += [node("pop", "while_pop", value_type="list-content", position=pop_position),
                 node("body", "construct_content", append_items=[{"type": "fixed", "value": ""}])]
        edges += [control("read", "pop"), control("pop", "body", "loop-out"), control("body", "pop", input_port="loop-in"),
                  data("input", "workflow:context_id", "pop", "context-id", "content")]
        previous = "pop"
    # A child-owned Context must be cleaned separately from the ancestor Context.
    body.append(node("local", "context_create", value_type="list-content", context_id="child-local"))
    edges += [control(previous, "local"), data("read", "value-out", "local", "initial-value", "list-content")]
    body.append(node("final", "context_read", value_type="list-content", context_id_source="fixed",
                     context_id="missing" if fail else "root-list"))
    edges += [control("local", "final"), control("final", "output"),
              data("final", "value-out", "output", "workflow:items", "list-content")]
    return graph("Leaf", body, edges)


def root(child):
    return graph("Root", [node("create", "context_create", value_type="list-content", context_id="root-list"),
                          call_node(child), node("after", "context_read", value_type="list-content")], [
        control("input", "create"), control("create", "call"), control("call", "after"), control("after", "output"),
        data("input", "workflow:items", "create", "initial-value", "list-content"),
        data("create", "context-id", "call", "workflow:context_id", "content"),
        data("input", "workflow:items", "call", "workflow:items", "list-content"),
        data("create", "context-id", "after", "context-id", "content"),
        data("after", "value-out", "output", "workflow:items", "list-content"),
    ])


class ChildContextTest(unittest.TestCase):
    def execute(self, document, documents):
        store = {}
        owners = {}
        popped = []
        cleanups = []
        client = MagicMock()
        def create(script, key_count, key, *args):
            if key in store:
                return 0
            store[key] = dict(zip(args[:-1:2], args[1:-1:2]))
            owners[key] = store[key]["invocation_id"]
            return 1
        client.eval.side_effect = create
        def pipeline():
            pipe = MagicMock()
            pipe.__enter__.return_value = pipe
            pipe.hgetall.side_effect = lambda key: dict(store.get(key, {}))
            pipe.hset.side_effect = lambda key, mapping: store[key].update(mapping)
            return pipe
        client.pipeline.side_effect = pipeline
        def delete(*keys):
            cleanups.append(set(keys))
            for key in keys:
                store.pop(key, None)
        client.delete.side_effect = delete
        compiled = parse_workflow(document)
        for item in compiled:
            item["_workflow_call_stack"] = ["Root"]
        propagate_workflow_output(compiled, compiled[0], "workflow:items", ["a", "b"])
        def propagate(current, source, port, value):
            if source["type"] == "while_pop" and port == "item-out":
                popped.append(value)
            return propagate_workflow_output(current, source, port, value)
        def read_document(name):
            self.assertIn("workflow-context:root-list", store)
            return copy.deepcopy(documents[name])
        with patch("workflow_context_repository.get_connection", return_value=client), \
             patch("workflow_parser._read_workspace_workflow_by_name", side_effect=read_document), \
             patch("workflow_nodes.propagate_workflow_output", side_effect=propagate), \
             patch("workflow_run_repository.record_process_workflow_run") as record:
            try:
                result = run_scheduled_workflow(compiled, 0)
            finally:
                self.assertEqual(store, {})
                self.assertEqual(cleanups, [{"workflow-context:child-local"}, {"workflow-context:root-list"}])
                self.assertNotEqual(owners["workflow-context:root-list"], owners["workflow-context:child-local"])
                self.assertNotIn("_workflow_ancestor_invocation_ids", compiled[0])
                self.assertEqual(len({c.args[0]["run_id"] for c in record.call_args_list}), len(documents) + 1)
        return result, popped

    def test_child_and_grandchild_read_write_ancestor_context(self):
        for nested in (False, True):
            with self.subTest(nested=nested):
                documents = {"Leaf": leaf()}
                if nested:
                    documents["Middle"] = wrapper("Middle", "Leaf")
                parent = root("Middle" if nested else "Leaf")
                for document in [parent, *documents.values()]:
                    validate_workflow(document)
                result, popped = self.execute(parent, documents)
                self.assertEqual(result, {"items": ["a", "b", "child"]})
                self.assertEqual(popped, [])

    def test_grandchild_pops_parent_list_and_parent_observes_empty_list(self):
        for position, expected in (("end", ["b", "a"]), ("start", ["a", "b"])):
            with self.subTest(position=position):
                documents = {"Leaf": leaf(position), "Middle": wrapper("Middle", "Leaf")}
                parent = root("Middle")
                for document in [parent, *documents.values()]:
                    validate_workflow(document)
                result, popped = self.execute(parent, documents)
                self.assertEqual(result, {"items": []})
                self.assertEqual(popped, expected)

    def test_nested_failure_cleans_only_each_invocations_own_contexts(self):
        with self.assertRaises(WorkflowContextError):
            self.execute(root("Middle"), {"Middle": wrapper("Middle", "Leaf"), "Leaf": leaf(fail=True)})


if __name__ == "__main__":
    unittest.main()
