"""Context-backed loop validation, atomic pops, and execution behavior."""

import copy
import json
import unittest
from unittest.mock import MagicMock, patch

import redis

from workflow_context_repository import WorkflowContextError, pop_context, write_context
from test_support import run_scheduled_workflow
from workflow_nodes import next_successor, nodes_map, propagate_workflow_output
from workflow_parser import parse_workflow
from workflow_structs import validate_struct_definitions
from workflow_validator import WorkflowValidationError, validate_workflow


def fixture(value_type="list-content", position=None, fixed=False):
    args = {"value_type": value_type}
    if position is not None:
        args["position"] = position
    if fixed:
        args.update(context_id_source="fixed", context_id="queue")
    inputs = [{"name": "items", "type": value_type}]
    outputs = [{"name": "remaining", "type": value_type}]
    nodes = [
        {"id": "input", "type": "input", "workflowPorts": [{"id": "workflow:items", **inputs[0]}]},
        {"id": "create", "type": "context_create", "arguments": {"value_type": value_type, "context_id": "queue"}},
        {"id": "pop", "type": "while_pop", "arguments": args},
        {"id": "body", "type": "construct_content", "arguments": {"append_items": [{"type": "fixed", "value": ""}]}},
        {"id": "read", "type": "context_read", "arguments": {"value_type": value_type}},
        {"id": "output", "type": "output", "workflowPorts": [{"id": "workflow:remaining", **outputs[0]}]},
    ]
    def edge(source, target, output="control-out", input_port="control-in", kind="control"):
        return {"fromId": source, "fromPortId": output, "toId": target, "toPortId": input_port, "type": kind}
    connections = [
        edge("input", "create"), edge("create", "pop"), edge("pop", "body", "loop-out"),
        edge("body", "pop", input_port="loop-in"), edge("pop", "read"), edge("read", "output"),
        edge("input", "create", "workflow:items", "initial-value", value_type),
        edge("create", "read", "context-id", "context-id", "content"),
        edge("read", "output", "value-out", "workflow:remaining", value_type),
    ]
    if not fixed:
        connections.append(edge("create", "pop", "context-id", "context-id", "content"))
    return {"schema_version": "2.0", "name": "pop_test", "input_ports": inputs, "output_ports": outputs,
            "nodes": nodes, "connections": connections}


def mock_pipeline(stored):
    pipeline = MagicMock()
    pipeline.__enter__.return_value = pipeline
    pipeline.hgetall.side_effect = lambda key: dict(stored)
    return pipeline


class WhilePopValidationTest(unittest.TestCase):
    def test_valid_lists_and_defaults(self):
        for kind in ("list-content", "list-message"):
            for position in (None, "start", "end"):
                for fixed in (False, True):
                    with self.subTest(kind=kind, position=position, fixed=fixed):
                        graph = fixture(kind, position, fixed)
                        validate_workflow(graph)
                        parsed = parse_workflow(graph)
                        self.assertEqual(parsed[2]["successors"], {"item": 3, "next": 4})
                        self.assertEqual(parsed[2]["predecessors"], {"last": [1], "continue": [3]})
                        self.assertEqual(set(parsed[2]["data_inputs"]), set() if fixed else {"context-id"})

    def test_invalid_configuration_and_input_types(self):
        for changes in (
            {"value_type": "content"}, {"value_type": "map-content"}, {"value_type": "list-struct:unknown"},
            {"position": "middle"}, {"context_id_source": "invalid"},
            {"context_id_source": "fixed"}, {"context_id_source": "fixed", "context_id": "   "},
        ):
            with self.subTest(changes=changes), self.assertRaises(WorkflowValidationError):
                graph = fixture()
                graph["nodes"][2]["arguments"].update(changes)
                validate_workflow(graph)
        graph = fixture()
        graph["connections"][-1]["type"] = "list-content"
        with self.assertRaisesRegex(WorkflowValidationError, "requires content"):
            validate_workflow(graph)
        graph = fixture()
        graph["connections"].pop()
        with self.assertRaisesRegex(WorkflowValidationError, "context-id"):
            validate_workflow(graph)

    def test_struct_list_declared_locally(self):
        # Struct lists stay internal to the workflow, never on boundary ports.
        graph = fixture()
        graph["nodes"][2]["arguments"] = {"value_type": "list-struct:task"}
        graph["metadata"] = {"structs": [{"id": "task", "name": "Task", "color": "#123456", "fields": []}]}
        validate_workflow(graph)
        self.assertIn("item-out", parse_workflow(graph)[2]["data_outputs"])


class PopContextTest(unittest.TestCase):
    def setUp(self):
        self.stored = {"value_type": "list-content", "value": '["a","b"]', "invocation_id": "run"}
        self.pipeline = mock_pipeline(self.stored)
        self.client = MagicMock()
        self.client.pipeline.return_value = self.pipeline
        self.connection = patch("workflow_context_repository.get_connection", return_value=self.client)
        self.connection.start()
        self.addCleanup(self.connection.stop)

    def test_pop_updates_list_in_transaction_and_refreshes_ttl(self):
        for position, item, remaining in (("end", "b", ["a"]), ("start", "a", ["b"])):
            with self.subTest(position=position), patch("workflow_context_repository._ttl_seconds", return_value=120):
                self.pipeline.reset_mock()
                self.assertEqual(pop_context("queue", "run", "list-content", position), (True, item))
                mapping = self.pipeline.hset.call_args.kwargs["mapping"]
                self.assertEqual(json.loads(mapping["value"]), remaining)
                self.assertIn("updated_at", mapping)
                self.pipeline.watch.assert_called_once_with("workflow-context:queue")
                self.pipeline.multi.assert_called_once_with()
                self.pipeline.expire.assert_called_once_with("workflow-context:queue", 120)
                self.pipeline.execute.assert_called_once_with()

    def test_empty_list_and_falsey_item_are_distinct(self):
        self.stored["value"] = '[]'
        self.assertEqual(pop_context("queue", "run", "list-content"), (False, None))
        self.pipeline.hset.assert_not_called()
        self.pipeline.execute.assert_called_once()
        self.stored["value"] = '[""]'
        self.assertEqual(pop_context("queue", "run", "list-content"), (True, ""))
        self.assertEqual(json.loads(self.pipeline.hset.call_args.kwargs["mapping"]["value"]), [])

    def test_conflict_retries_using_latest_list(self):
        self.pipeline.hgetall.side_effect = [dict(self.stored), {**self.stored, "value": '["a","new"]'}]
        self.pipeline.execute.side_effect = [redis.WatchError(), []]
        self.assertEqual(pop_context("queue", "run", "list-content"), (True, "new"))
        self.assertEqual(self.pipeline.watch.call_count, 2)

    def test_conflict_rechecks_an_empty_list(self):
        self.pipeline.hgetall.side_effect = [{**self.stored, "value": '[]'}, dict(self.stored)]
        self.pipeline.execute.side_effect = [redis.WatchError(), []]
        self.assertEqual(pop_context("queue", "run", "list-content"), (True, "b"))

    def test_invalid_context_or_value_never_mutates(self):
        for changes in ({"invocation_id": "other"}, {"value_type": "list-message"},
                        {"value": "not json"}, {"value": '{}'}, {"value": '[1]'}):
            with self.subTest(changes=changes):
                self.pipeline.reset_mock()
                self.pipeline.hgetall.side_effect = None
                self.pipeline.hgetall.return_value = {**self.stored, **changes}
                with self.assertRaises(WorkflowContextError):
                    pop_context("queue", "run", "list-content")
                self.pipeline.multi.assert_not_called()
        self.pipeline.hgetall.return_value = {}
        with self.assertRaises(WorkflowContextError):
            pop_context("queue", "run", "list-content")

    def test_struct_list_is_validated_before_pop(self):
        defs = validate_struct_definitions([{"id": "task", "name": "Task", "color": "#123456",
            "fields": [{"name": "name", "type": "content", "required": True}]}])
        self.stored.update(value_type="list-struct:task", value='[{"name":"first"},{"name":"last"}]')
        self.assertEqual(pop_context("queue", "run", "list-struct:task", struct_definitions=defs), (True, {"name": "last"}))
        self.stored["value"] = '[{}]'
        with self.assertRaises(WorkflowContextError):
            pop_context("queue", "run", "list-struct:task", struct_definitions=defs)

    def test_redis_failure_is_wrapped(self):
        self.pipeline.execute.side_effect = redis.ConnectionError("offline")
        with self.assertRaises(WorkflowContextError):
            pop_context("queue", "run", "list-content")


class WhilePopExecutionTest(unittest.TestCase):
    def execute(self, values, position=None, fixed=False, append_during_body=False, kind="list-content"):
        original_values = copy.deepcopy(values)
        graph = fixture(kind, position, fixed)
        validate_workflow(graph)
        workflow_map = parse_workflow(graph)
        propagate_workflow_output(workflow_map, workflow_map[0], "workflow:items", copy.deepcopy(values))
        stored = {}
        pipeline = mock_pipeline(stored)
        pipeline.hset.side_effect = lambda key, mapping: stored.update(mapping)
        client = MagicMock()
        client.pipeline.return_value = pipeline
        def create(invocation_id, value_type, value, context_id, definitions):
            stored.update(invocation_id=invocation_id, value_type=value_type, value=json.dumps(value))
            return context_id
        seen = []
        def body(index, current_map):
            # Read the actual stored list after pop and optionally enqueue new work.
            item = copy.deepcopy(current_map[index].get("_last_item"))
            seen.append(item)
            if append_during_body and len(seen) == 1:
                write_context("queue", stored["invocation_id"], kind, json.loads(stored["value"]) + ["new"])
            return next_successor(current_map[index])
        workflow_map[3]["data_inputs"] = {"item": [2, "item-out", None]}
        workflow_map[2]["data_outputs"]["item-out"] = [[3, "item"]]
        def capture(index, current_map):
            current_map[index]["_last_item"] = current_map[index]["data_inputs"]["item"][2]
            return body(index, current_map)
        with patch("workflow_context_repository.create_context", side_effect=create), \
             patch("workflow_context_repository.get_connection", return_value=client), \
             patch.dict(nodes_map, {"construct_content": capture}):
            result = run_scheduled_workflow(workflow_map, 0)
        client.delete.assert_called_once_with("workflow-context:queue")
        self.assertEqual(result, {"remaining": []})
        self.assertEqual(json.loads(stored["value"]), [])
        self.assertEqual(values, original_values)
        return seen

    def test_pop_order_and_empty_list(self):
        for position, expected in ((None, ["c", "b", "a"]), ("end", ["c", "b", "a"]), ("start", ["a", "b", "c"])):
            for fixed in (False, True):
                with self.subTest(position=position, fixed=fixed):
                    self.assertEqual(self.execute(["a", "b", "c"], position, fixed), expected)
        self.assertEqual(self.execute([]), [])
        self.assertEqual(self.execute([""]), [""])

    def test_next_iteration_observes_changes_from_body(self):
        self.assertEqual(self.execute(["a", "b"], append_during_body=True), ["b", "new", "a"])

    def test_message_items(self):
        for kind, values in (("list-message", [{"role": "user", "content": "one"}, {"role": "assistant", "content": "two"}]),):
            with self.subTest(kind=kind):
                self.assertEqual(self.execute(values, kind=kind), values[::-1])


if __name__ == "__main__":
    unittest.main()
