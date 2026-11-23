"""Native Message construction and typed-port compatibility."""
import copy
import json
import unittest

from workflow_contract import data_ports_for_node, is_valid_connection
from workflow_nodes import workflow_construct_message
from workflow_parser import parse_workflow
from workflow_validator import validate_workflow


CALL = {"id": "call-1", "type": "function", "function": {
    "name": "workspace.get_file", "arguments": '{"file_id":"file-a"}',
}}


def message_graph(role="assistant", **values):
    return [
        {"id": "message", "type": "construct_message", "arguments": {"role": role},
         "successors": {"next": 1},
         "data_inputs": {name: [None, None, value] for name, value in values.items()},
         "data_outputs": {"content-out": [[1, "content-in"]]}},
        {"data_inputs": {"content-in": [0, "content-out", None]}},
    ]


def build(role="assistant", **values):
    graph = message_graph(role, **{"content-in": "answer", **values})
    before = copy.deepcopy(graph[0]["data_inputs"])
    assert workflow_construct_message(0, graph) == 1
    assert graph[0]["data_inputs"] == before
    return json.loads(graph[1]["data_inputs"]["content-in"][2])


class MessageConstructionTest(unittest.TestCase):
    def test_plain_messages_remain_compatible(self):
        for role in ("system", "user", "assistant", "tool"):
            with self.subTest(role=role):
                self.assertEqual(build(role), {"role": role, "content": "answer"})

    def test_reasoning_survives_without_calls_and_empty_calls_are_omitted(self):
        self.assertEqual(build(**{"reasoning-in": "reasoning", "tool-calls-in": []}),
                         {"role": "assistant", "content": "answer", "reasoning_content": "reasoning"})
        self.assertEqual(build(**{"reasoning-in": ""})["reasoning_content"], "")

    def test_calls_are_objects_with_original_argument_strings_and_extensions(self):
        call = {**CALL, "provider_extension": {"signature": "opaque"}}
        result = build(**{"content-in": "", "reasoning-in": "thinking",
                          "tool-calls-in": [json.dumps(call, ensure_ascii=False), json.dumps(CALL)]})
        self.assertEqual(result["tool_calls"], [call, CALL])
        self.assertIsInstance(result["tool_calls"][0], dict)
        self.assertIsInstance(result["tool_calls"][0]["function"]["arguments"], str)
        self.assertEqual(result["reasoning_content"], "thinking")

    def test_tool_result_preserves_matching_id(self):
        self.assertEqual(build("tool", **{"tool-call-id-in": "call-1"}),
                         {"role": "tool", "content": "answer", "tool_call_id": "call-1"})

    def test_dynamic_role_uses_same_message_fields(self):
        graph = message_graph("user", **{"content-in": "", "role-in": "assistant",
                                        "tool-calls-in": [json.dumps(CALL)]})
        graph[0]["arguments"]["role_source"] = "port"
        workflow_construct_message(0, graph)
        self.assertEqual(json.loads(graph[1]["data_inputs"]["content-in"][2])["tool_calls"], [CALL])

    def test_invalid_field_types_and_roles_fail_at_message_node(self):
        cases = [
            ("user", {"reasoning-in": "thinking"}),
            ("tool", {"tool-calls-in": []}),
            ("assistant", {"tool-call-id-in": "call-1"}),
            ("assistant", {"reasoning-in": 1}),
            ("assistant", {"content-in": {"text": "answer"}}),
            ("tool", {"tool-call-id-in": ""}),
            ("assistant", {"tool-calls-in": [CALL]}),
            ("assistant", {"tool-calls-in": ["not json"]}),
            ("assistant", {"tool-calls-in": ["[]"]}),
            ("assistant", {"tool-calls-in": ['{"id":"call-1"}']}),
            ("assistant", {"tool-calls-in": [json.dumps({**CALL, "function": {"name": "test", "arguments": {}}})]}),
        ]
        for role, values in cases:
            with self.subTest(role=role, values=values), self.assertRaisesRegex(ValueError, "construct_message"):
                build(role, **values)

    def test_message_ports_validate_compile_and_keep_calls_list_typed(self):
        document = {
            "schema_version": "2.0",
            "input_ports": [{"name": "content", "type": "content"}, {"name": "calls", "type": "list-content"}],
            "output_ports": [{"name": "message", "type": "content"}],
            "nodes": [
                {"id": "input", "type": "input", "workflowPorts": [{"id": "workflow:content", "name": "content", "type": "content"}, {"id": "workflow:calls", "name": "calls", "type": "list-content"}]},
                {"id": "message", "type": "construct_message", "arguments": {"role": "assistant"}},
                {"id": "output", "type": "output", "workflowPorts": [{"id": "workflow:message", "name": "message", "type": "content"}]},
            ],
            "connections": [
                {"fromId": "input", "fromPortId": "control-out", "toId": "message", "toPortId": "control-in", "type": "control"},
                {"fromId": "message", "fromPortId": "control-out", "toId": "output", "toPortId": "control-in", "type": "control"},
                {"fromId": "input", "fromPortId": "workflow:content", "toId": "message", "toPortId": "content-in", "type": "content"},
                {"fromId": "input", "fromPortId": "workflow:calls", "toId": "message", "toPortId": "tool-calls-in", "type": "list-content"},
                {"fromId": "message", "fromPortId": "content-out", "toId": "output", "toPortId": "workflow:message", "type": "content"},
            ],
        }
        validate_workflow(document)
        graph = parse_workflow(document)
        self.assertIn("tool-calls-in", graph[1]["data_inputs"])
        nodes = {node["id"]: node for node in document["nodes"]}
        nodes["input"]["workflowPorts"] = [{"id": "workflow:calls", "name": "calls", "type": "list-content"}]
        call_edge = document["connections"][3]
        self.assertTrue(is_valid_connection(call_edge, nodes, document["input_ports"], document["output_ports"]))
        self.assertFalse(is_valid_connection({**call_edge, "type": "content"}, nodes, document["input_ports"], document["output_ports"]))
        inputs, _ = data_ports_for_node(nodes["message"], [], [])
        self.assertTrue({"reasoning-in", "tool-calls-in", "tool-call-id-in"} <= inputs)


if __name__ == "__main__":
    unittest.main()
