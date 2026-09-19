import unittest
from unittest.mock import patch

from workflow_contract import is_valid_connection
from workflow_parser import parse_workflow
from workflow_nodes import (
    run_workflow_map,
    workflow_content_map,
    workflow_construct_list,
    workflow_construct_message,
    workflow_deserialize_json,
    workflow_llm,
    workflow_split_event,
)
from workflow_validator import WorkflowValidationError, validate_workflow


def callable_workflow_fixture() -> dict:
    return {
        "input_ports": [{"name": "query", "type": "content"}],
        "output_ports": [{"name": "result", "type": "content"}],
        "nodes": [
            {
                "id": "input",
                "type": "input",
                "name": "Input",
                "workflowPorts": [{"id": "workflow:query", "name": "query", "type": "content"}],
            },
            {
                "id": "call-summary",
                "type": "workflow",
                "name": "Summary",
                "arguments": {"workflow_name": "Summary"},
                "input_ports": [{"name": "query", "type": "content"}],
                "output_ports": [{"name": "result", "type": "content"}],
            },
            {
                "id": "output",
                "type": "output",
                "name": "Output",
                "workflowPorts": [{"id": "workflow:result", "name": "result", "type": "content"}],
            },
        ],
        "connections": [
            {"id": "control-input-call", "fromId": "input", "fromPortId": "control-out", "toId": "call-summary", "toPortId": "control-in", "type": "control"},
            {"id": "control-call-output", "fromId": "call-summary", "fromPortId": "control-out", "toId": "output", "toPortId": "control-in", "type": "control"},
            {"id": "query-input-call", "fromId": "input", "fromPortId": "workflow:query", "toId": "call-summary", "toPortId": "workflow:query", "type": "content"},
            {"id": "result-call-output", "fromId": "call-summary", "fromPortId": "workflow:result", "toId": "output", "toPortId": "workflow:result", "type": "content"},
        ],
    }


class CallableWorkflowNodeTest(unittest.TestCase):
    def test_construct_message_role_port_requires_content_connection(self):
        nodes_by_id = {
            "input": {
                "id": "input",
                "type": "input",
                "workflowPorts": [
                    {"id": "workflow:role", "name": "role", "type": "message"}
                ],
            },
            "message": {
                "id": "message",
                "type": "construct_message",
                "arguments": {"role_source": "port", "role": "user"},
            },
        }
        connection = {
            "fromId": "input",
            "fromPortId": "workflow:role",
            "toId": "message",
            "toPortId": "role-in",
            "type": "message",
        }

        self.assertFalse(
            is_valid_connection(
                connection,
                nodes_by_id,
                [{"name": "role", "type": "message"}],
                [],
            )
        )

    def test_validator_reads_construct_list_item_type_from_arguments(self):
        workflow = {
            "input_ports": [{"name": "value", "type": "content"}],
            "output_ports": [{"name": "values", "type": "list-content"}],
            "nodes": [
                {
                    "id": "input",
                    "type": "input",
                    "workflowPorts": [
                        {
                            "id": "workflow:value",
                            "name": "value",
                            "type": "content",
                        }
                    ],
                },
                {
                    "id": "list",
                    "type": "construct_list",
                    "arguments": {
                        "item_type": "content",
                        "initial_value_count": 1,
                    },
                    "dataInputPorts": ["content-in-0"],
                },
                {
                    "id": "output",
                    "type": "output",
                    "workflowPorts": [
                        {
                            "id": "workflow:values",
                            "name": "values",
                            "type": "list-content",
                        }
                    ],
                },
            ],
            "connections": [
                {
                    "fromId": "input",
                    "fromPortId": "control-out",
                    "toId": "list",
                    "toPortId": "control-in",
                    "type": "control",
                },
                {
                    "fromId": "list",
                    "fromPortId": "control-out",
                    "toId": "output",
                    "toPortId": "control-in",
                    "type": "control",
                },
                {
                    "fromId": "input",
                    "fromPortId": "workflow:value",
                    "toId": "list",
                    "toPortId": "content-in-0",
                    "type": "content",
                },
                {
                    "fromId": "list",
                    "fromPortId": "list-out",
                    "toId": "output",
                    "toPortId": "workflow:values",
                    "type": "list-content",
                },
            ],
        }

        validate_workflow(workflow)

    def test_llm_accepts_list_message_input(self):
        workflow = {
            "input_ports": [{"name": "messages", "type": "list-message"}],
            "output_ports": [],
            "nodes": [
                {
                    "id": "input",
                    "type": "input",
                    "workflowPorts": [
                        {
                            "id": "workflow:messages",
                            "name": "messages",
                            "type": "list-message",
                        }
                    ],
                },
                {
                    "id": "llm",
                    "type": "llm",
                    "arguments": {
                        "model": "",
                        "think": False,
                        "tool_calls": False,
                        "tools": [],
                    },
                },
                {"id": "output", "type": "output", "workflowPorts": []},
            ],
            "connections": [
                {
                    "fromId": "input",
                    "fromPortId": "control-out",
                    "toId": "llm",
                    "toPortId": "control-in",
                    "type": "control",
                },
                {
                    "fromId": "llm",
                    "fromPortId": "control-out",
                    "toId": "output",
                    "toPortId": "control-in",
                    "type": "control",
                },
                {
                    "fromId": "input",
                    "fromPortId": "workflow:messages",
                    "toId": "llm",
                    "toPortId": "messages-in",
                    "type": "list-message",
                },
            ],
        }

        validate_workflow(workflow)
        parsed = parse_workflow(workflow)

        self.assertEqual(
            parsed[1]["data_inputs"]["messages-in"],
            [0, "workflow:messages", None],
        )

        workflow["input_ports"][0]["type"] = "message"
        workflow["nodes"][0]["workflowPorts"][0]["type"] = "message"
        workflow["connections"][2]["type"] = "message"
        with self.assertRaisesRegex(
            WorkflowValidationError,
            "llm messages-in input requires list-message data",
        ):
            validate_workflow(workflow)

    def test_validator_and_parser_accept_history_node(self):
        workflow = {
            "input_ports": [],
            "output_ports": [{"name": "events", "type": "event-list"}],
            "nodes": [
                {"id": "input", "type": "input", "workflowPorts": []},
                {
                    "id": "history",
                    "type": "history",
                    "arguments": {"event_types": ["terminal", "response"], "limit": 5},
                },
                {
                    "id": "output",
                    "type": "output",
                    "workflowPorts": [
                        {"id": "workflow:events", "name": "events", "type": "event-list"}
                    ],
                },
            ],
            "connections": [
                {"fromId": "input", "fromPortId": "control-out", "toId": "history", "toPortId": "control-in", "type": "control"},
                {"fromId": "history", "fromPortId": "control-out", "toId": "output", "toPortId": "control-in", "type": "control"},
                {"fromId": "history", "fromPortId": "events", "toId": "output", "toPortId": "workflow:events", "type": "event-list"},
            ],
        }

        validate_workflow(workflow)
        parsed = parse_workflow(workflow)

        self.assertEqual(
            parsed[1]["arguments"],
            {"event_types": ["terminal", "response"], "limit": 5},
        )
        self.assertEqual(parsed[1]["data_outputs"]["events"], [[2, "workflow:events"]])

    def test_validator_accepts_history_event_list_to_foreach(self):
        workflow = {
            "input_ports": [],
            "output_ports": [],
            "nodes": [
                {"id": "input", "type": "input", "workflowPorts": []},
                {
                    "id": "history",
                    "type": "history",
                    "arguments": {"event_types": ["response"], "limit": 5},
                },
                {
                    "id": "foreach",
                    "type": "foreach",
                    "arguments": {"item_type": "event"},
                },
            ],
            "connections": [
                {"fromId": "input", "fromPortId": "control-out", "toId": "history", "toPortId": "control-in", "type": "control"},
                {"fromId": "history", "fromPortId": "events", "toId": "foreach", "toPortId": "list-in", "type": "event-list"},
            ],
        }

        validate_workflow(workflow)

    def test_validator_and_parser_accept_split_event_node(self):
        workflow = {
            "input_ports": [{"name": "event", "type": "event"}],
            "output_ports": [
                {"name": "type", "type": "content"},
                {"name": "payload", "type": "content"},
            ],
            "nodes": [
                {
                    "id": "input",
                    "type": "input",
                    "workflowPorts": [
                        {"id": "workflow:event", "name": "event", "type": "event"}
                    ],
                },
                {"id": "split", "type": "split_event", "arguments": {}},
                {
                    "id": "output",
                    "type": "output",
                    "workflowPorts": [
                        {"id": "workflow:type", "name": "type", "type": "content"},
                        {"id": "workflow:payload", "name": "payload", "type": "content"},
                    ],
                },
            ],
            "connections": [
                {"fromId": "input", "fromPortId": "control-out", "toId": "split", "toPortId": "control-in", "type": "control"},
                {"fromId": "split", "fromPortId": "control-out", "toId": "output", "toPortId": "control-in", "type": "control"},
                {"fromId": "input", "fromPortId": "workflow:event", "toId": "split", "toPortId": "event-in", "type": "event"},
                {"fromId": "split", "fromPortId": "type-out", "toId": "output", "toPortId": "workflow:type", "type": "content"},
                {"fromId": "split", "fromPortId": "payload-out", "toId": "output", "toPortId": "workflow:payload", "type": "content"},
            ],
        }

        validate_workflow(workflow)
        parsed = parse_workflow(workflow)

        self.assertEqual(parsed[1]["data_inputs"]["event-in"], [0, "workflow:event", None])
        self.assertEqual(
            parsed[1]["data_outputs"],
            {
                "type-out": [[2, "workflow:type"]],
                "payload-out": [[2, "workflow:payload"]],
            },
        )

        invalid_connection = dict(workflow["connections"][2], type="content")
        self.assertFalse(
            is_valid_connection(
                invalid_connection,
                {node["id"]: node for node in workflow["nodes"]},
                workflow["input_ports"],
                workflow["output_ports"],
            )
        )

    def test_validator_rejects_history_limit_out_of_range(self):
        workflow = callable_workflow_fixture()
        workflow["nodes"][1] = {
            "id": "history",
            "type": "history",
            "arguments": {"event_types": ["response"], "limit": 0},
        }

        with self.assertRaisesRegex(WorkflowValidationError, "limit must be an integer from 1 to 1000"):
            validate_workflow(workflow)

    def test_validator_rejects_invalid_history_event_types(self):
        for event_types in ([], ["workflow"], ["response", "response"]):
            with self.subTest(event_types=event_types):
                workflow = callable_workflow_fixture()
                workflow["nodes"][1] = {
                    "id": "history",
                    "type": "history",
                    "arguments": {"event_types": event_types, "limit": 10},
                }

                with self.assertRaisesRegex(
                    WorkflowValidationError,
                    "event_types must contain unique terminal or response values",
                ):
                    validate_workflow(workflow)

    def test_parser_uses_named_control_flow_dictionaries(self):
        workflow = {
            "input_ports": [],
            "output_ports": [],
            "nodes": [
                {"id": "input", "type": "input", "workflowPorts": []},
                {
                    "id": "router",
                    "type": "router",
                    "arguments": {
                        "branches": [
                            {"id": "route-yes", "name": "yes"},
                            {"id": "route-no", "name": "no"},
                        ],
                    },
                },
                {"id": "foreach", "type": "foreach", "arguments": {"item_type": "content"}},
                {"id": "output", "type": "output", "workflowPorts": []},
            ],
            "connections": [
                {"fromId": "input", "fromPortId": "control-out", "toId": "router", "toPortId": "control-in", "type": "control"},
                {"fromId": "router", "fromPortId": "route-yes", "toId": "foreach", "toPortId": "control-in", "type": "control"},
                {"fromId": "router", "fromPortId": "route-no", "toId": "output", "toPortId": "control-in", "type": "control"},
                {"fromId": "foreach", "fromPortId": "loop-out", "toId": "foreach", "toPortId": "loop-in", "type": "control"},
                {"fromId": "foreach", "fromPortId": "control-out", "toId": "output", "toPortId": "control-in", "type": "control"},
            ],
        }

        parsed = parse_workflow(workflow)

        self.assertEqual(parsed[0]["successors"], {"next": 1})
        self.assertEqual(parsed[1]["predecessors"], {"last": [0]})
        self.assertEqual(
            parsed[1]["successors"], {"branch-yes": 2, "branch-no": 3}
        )
        self.assertNotIn("branches", parsed[1])
        self.assertEqual(
            parsed[1]["arguments"]["branches"],
            [
                {"id": "route-yes", "name": "yes"},
                {"id": "route-no", "name": "no"},
            ],
        )
        self.assertEqual(
            parsed[2]["predecessors"], {"last": [1], "continue": [2]}
        )
        self.assertEqual(parsed[2]["successors"], {"item": 2, "next": 3})
        self.assertEqual(parsed[3]["predecessors"], {"last": [1, 2]})

    def test_validator_rejects_duplicate_router_branch_names(self):
        workflow = callable_workflow_fixture()
        workflow["nodes"].insert(
            1,
            {
                "id": "router",
                "type": "router",
                "arguments": {
                    "branches": [
                        {"id": "route-a", "name": "same"},
                        {"id": "route-b", "name": "same"},
                    ],
                },
            },
        )

        with self.assertRaisesRegex(WorkflowValidationError, "duplicate names"):
            validate_workflow(workflow)

    def test_validator_rejects_flattened_node_arguments(self):
        workflow = callable_workflow_fixture()
        workflow["nodes"][1]["workflow_name"] = "Summary"

        with self.assertRaisesRegex(WorkflowValidationError, "must be inside arguments"):
            validate_workflow(workflow)

    def test_validator_rejects_removed_tool_call_node(self):
        workflow = callable_workflow_fixture()
        workflow["nodes"][1] = {
            "id": "tool-call",
            "type": "tool_call",
            "name": "Tool Call",
            "arguments": {},
        }

        with self.assertRaisesRegex(WorkflowValidationError, "unsupported node type: tool_call"):
            validate_workflow(workflow)

    def test_validator_rejects_shared_fields_inside_arguments(self):
        workflow = callable_workflow_fixture()
        workflow["nodes"][1]["arguments"]["input_ports"] = workflow["nodes"][1].pop("input_ports")

        with self.assertRaisesRegex(WorkflowValidationError, "shared fields must be top-level"):
            validate_workflow(workflow)

    def test_validator_and_parser_accept_callable_workflow_ports(self):
        workflow = callable_workflow_fixture()

        validate_workflow(workflow)
        parsed = parse_workflow(workflow)

        self.assertEqual(
            parsed[1]["data_inputs"]["workflow:query"],
            [0, "workflow:query", None],
        )
        self.assertEqual(parsed[1]["data_outputs"]["workflow:result"], [[2, "workflow:result"]])
        self.assertEqual(parsed[1]["arguments"]["workflow_name"], "Summary")
        self.assertEqual(
            parsed[1]["input_ports"],
            [{"name": "query", "type": "content"}],
        )
        self.assertEqual(
            parsed[1]["output_ports"],
            [{"name": "result", "type": "content"}],
        )
        self.assertNotIn("input_ports", parsed[1]["arguments"])
        self.assertNotIn("output_ports", parsed[1]["arguments"])
        self.assertNotIn("workflow_id", parsed[1])
        self.assertEqual(
            parsed[0]["workflowPorts"],
            [{"id": "workflow:query", "name": "query", "type": "content"}],
        )
        self.assertEqual(
            parsed[2]["workflowPorts"],
            [{"id": "workflow:result", "name": "result", "type": "content"}],
        )

    def test_validator_filters_wrong_callable_workflow_port_type(self):
        workflow = callable_workflow_fixture()
        workflow["connections"][2]["type"] = "message"

        validate_workflow(workflow)
        parsed = parse_workflow(workflow)
        self.assertEqual(
            parsed[1]["data_inputs"]["workflow:query"], [None, None, None]
        )

    def test_parser_filters_connection_invalidated_by_metadata(self):
        workflow = callable_workflow_fixture()
        workflow["connections"].append({
            "id": "stale",
            "fromId": "input",
            "fromPortId": "workflow:stale",
            "toId": "call-summary",
            "toPortId": "workflow:query",
            "type": "content",
        })

        parsed = parse_workflow(workflow)

        self.assertNotIn([1, "workflow:query"], parsed[0]["data_outputs"]["workflow:query"])

    def test_validator_filters_legacy_output_content_input(self):
        workflow = callable_workflow_fixture()
        workflow["connections"][3]["toPortId"] = "content-in"

        validate_workflow(workflow)
        self.assertIsNone(parse_workflow(workflow)[1]["data_inputs"]["workflow:result"])

    def test_validator_filters_legacy_input_content_output(self):
        workflow = callable_workflow_fixture()
        workflow["connections"][2]["fromPortId"] = "content-out"

        validate_workflow(workflow)
        self.assertEqual(parse_workflow(workflow)[0]["data_outputs"]["workflow:query"], [])

    def test_validator_rejects_boundary_without_workflow_ports(self):
        workflow = callable_workflow_fixture()
        del workflow["nodes"][0]["workflowPorts"]

        with self.assertRaisesRegex(WorkflowValidationError, "workflowPorts is required"):
            validate_workflow(workflow)

    def test_validator_rejects_boundary_ports_that_differ_from_metadata(self):
        workflow = callable_workflow_fixture()
        workflow["nodes"][0]["workflowPorts"] = []

        with self.assertRaisesRegex(WorkflowValidationError, "must match workflow input_ports"):
            validate_workflow(workflow)

    def test_validator_requires_boundary_metadata(self):
        workflow = callable_workflow_fixture()
        del workflow["input_ports"]

        with self.assertRaisesRegex(WorkflowValidationError, "workflow.input_ports must be a list"):
            validate_workflow(workflow)

    def test_validator_rejects_multiple_input_nodes(self):
        workflow = callable_workflow_fixture()
        workflow["nodes"].append({
            "id": "input-duplicate",
            "type": "input",
            "name": "Input duplicate",
            "workflowPorts": [],
        })

        with self.assertRaisesRegex(WorkflowValidationError, "exactly one input"):
            validate_workflow(workflow)

    def test_validator_rejects_duplicate_callable_input_port_names(self):
        workflow = callable_workflow_fixture()
        workflow["nodes"][1]["input_ports"].append({"name": " Query ", "type": "message"})

        with self.assertRaisesRegex(WorkflowValidationError, "input_ports contains duplicate names"):
            validate_workflow(workflow)

    def test_validator_rejects_duplicate_callable_output_port_names(self):
        workflow = callable_workflow_fixture()
        workflow["nodes"][1]["output_ports"].append({"name": "RESULT", "type": "message"})

        with self.assertRaisesRegex(WorkflowValidationError, "output_ports contains duplicate names"):
            validate_workflow(workflow)

    def test_validator_allows_same_name_on_input_and_output(self):
        workflow = callable_workflow_fixture()
        workflow["nodes"][1]["output_ports"] = [{"name": "query", "type": "content"}]
        workflow["connections"][3]["fromPortId"] = "workflow:query"

        validate_workflow(workflow)


class WorkflowExecutionTest(unittest.TestCase):
    def test_content_map_outputs_mapped_value(self):
        workflow_map = [
            {
                "id": "map",
                "type": "content_map",
                "arguments": {
                    "mappings": [
                        {"key": "pending", "value": "处理中"},
                        {"key": "done", "value": "已完成"},
                    ]
                },
                "successors": {"next": 1},
                "data_inputs": {"content-in": [None, None, "done"]},
                "data_outputs": {"content-out": [[1, "result"]]},
            },
            {"data_inputs": {"result": [0, "content-out", None]}},
        ]

        workflow_content_map(0, workflow_map)

        self.assertEqual(workflow_map[1]["data_inputs"]["result"][2], "已完成")

    def test_content_map_rejects_unmapped_key(self):
        workflow_map = [
            {
                "id": "map",
                "type": "content_map",
                "arguments": {"mappings": [{"key": "done", "value": "已完成"}]},
                "successors": {"next": 1},
                "data_inputs": {"content-in": [None, None, "missing"]},
                "data_outputs": {"content-out": []},
            },
            {},
        ]

        with self.assertRaisesRegex(ValueError, "key is not mapped"):
            workflow_content_map(0, workflow_map)

    def test_construct_message_reads_role_from_port(self):
        workflow_map = [
            {
                "id": "message",
                "type": "construct_message",
                "arguments": {"role_source": "port", "role": "user"},
                "successors": {"next": 1},
                "data_inputs": {
                    "content-in": [None, None, "hello"],
                    "role-in": [None, None, "assistant"],
                },
                "data_outputs": {"message-out": [[1, "message-in"]]},
            },
            {"data_inputs": {"message-in": [0, "message-out", None]}},
        ]

        workflow_construct_message(0, workflow_map)

        self.assertEqual(
            workflow_map[1]["data_inputs"]["message-in"][2],
            {"role": "assistant", "content": "hello"},
        )

    def test_construct_message_rejects_missing_port_role(self):
        workflow_map = [
            {
                "id": "message",
                "type": "construct_message",
                "arguments": {"role_source": "port", "role": "user"},
                "successors": {"next": 1},
                "data_inputs": {"content-in": [None, None, "hello"]},
                "data_outputs": {"message-out": []},
            },
            {},
        ]

        with self.assertRaisesRegex(ValueError, "role input is missing"):
            workflow_construct_message(0, workflow_map)

    def test_construct_list_preserves_declared_port_order(self):
        workflow_map = [
            {
                "id": "messages",
                "type": "construct_list",
                "arguments": {"item_type": "message", "initial_value_count": 2},
                "successors": {"next": 1},
                "data_inputs": {
                    "message-in-1": [None, None, {"role": "user", "content": "second"}],
                    "message-in-0": [None, None, {"role": "system", "content": "first"}],
                },
                "data_outputs": {"list-out": [[1, "messages-in"]]},
            },
            {
                "id": "llm",
                "data_inputs": {"messages-in": [0, "list-out", None]},
            },
        ]

        workflow_construct_list(0, workflow_map)

        self.assertEqual(
            workflow_map[1]["data_inputs"]["messages-in"][2],
            [
                {"role": "system", "content": "first"},
                {"role": "user", "content": "second"},
            ],
        )

    def test_llm_rejects_missing_or_invalid_messages(self):
        base_node = {
            "id": "llm",
            "type": "llm",
            "arguments": {"tools": []},
            "successors": {"next": 1},
            "data_outputs": {"output": []},
        }
        invalid_values = [None, [], [{"role": "user"}], ["not-a-message"]]

        for value in invalid_values:
            with self.subTest(value=value):
                workflow_map = [
                    {
                        **base_node,
                        "data_inputs": {"messages-in": [None, None, value]},
                    },
                    {},
                ]
                with self.assertRaisesRegex(ValueError, "llm messages input"):
                    workflow_llm(0, workflow_map)

    def test_list_append_outputs_new_list_without_mutating_input(self):
        for position, expected in (("start", ["new", "first"]), ("end", ["first", "new"])):
            with self.subTest(position=position):
                input_items = ["first"]
                workflow_map = [
                    {
                        "id": "append",
                        "type": "list_append",
                        "arguments": {"item_type": "content", "position": position},
                        "successors": {"next": 1},
                        "data_inputs": {
                            "list-in": [None, None, input_items],
                            "item-in": [None, None, "new"],
                        },
                        "data_outputs": {"list-out": [[1, "workflow:result"]]},
                    },
                    {
                        "id": "output",
                        "type": "output",
                        "workflowPorts": [
                            {"id": "workflow:result", "name": "result", "type": "list-content"}
                        ],
                        "successors": {},
                        "data_inputs": {"workflow:result": [0, "list-out", None]},
                        "data_outputs": {},
                    },
                ]

                result = run_workflow_map(workflow_map, 0)["result"]

                self.assertEqual(result, expected)
                self.assertIsNot(result, input_items)
                self.assertEqual(input_items, ["first"])

    def test_run_workflow_map_traverses_to_output(self):
        workflow_map = [
            {
                "id": "input",
                "type": "input",
                "successors": {"next": 1},
                "data_inputs": {},
                "data_outputs": {},
            },
            {
                "id": "content",
                "type": "construct_content",
                "arguments": {"append_items": [{"type": "fixed", "value": "done"}]},
                "successors": {"next": 2},
                "data_inputs": {},
                "data_outputs": {"content-out": [[2, "workflow:result"]]},
            },
            {
                "id": "output",
                "type": "output",
                "workflowPorts": [
                    {"id": "workflow:result", "name": "result", "type": "content"}
                ],
                "successors": {},
                "data_inputs": {"workflow:result": [1, "content-out", None]},
                "data_outputs": {},
            },
        ]

        self.assertEqual(run_workflow_map(workflow_map, 0), {"result": "done"})

    @patch("workflow_context_repository.delete_contexts")
    @patch("workflow_context_repository.create_context")
    def test_run_workflow_map_cleans_created_contexts_on_success(
        self, create_context, delete_contexts
    ):
        create_context.return_value = "ctx-parent"
        workflow_map = [
            {
                "id": "create",
                "type": "context_create",
                "arguments": {"value_type": "content"},
                "successors": {"next": 1},
                "data_inputs": {"initial-value": [None, None, "value"]},
                "data_outputs": {"context-id": []},
            },
            {
                "id": "output",
                "type": "output",
                "workflowPorts": [],
                "successors": {},
                "data_inputs": {},
                "data_outputs": {},
            },
        ]

        self.assertEqual(run_workflow_map(workflow_map, 0), {})

        invocation_id = create_context.call_args.args[0]
        self.assertIsInstance(invocation_id, str)
        self.assertTrue(invocation_id)
        delete_contexts.assert_called_once_with({"ctx-parent"})
        self.assertNotIn("_workflow_invocation_id", workflow_map[0])
        self.assertNotIn("_workflow_context_ids", workflow_map[0])

    @patch("workflow_context_repository.delete_contexts")
    @patch("workflow_context_repository.create_context")
    def test_run_workflow_map_cleans_created_contexts_on_failure(
        self, create_context, delete_contexts
    ):
        create_context.return_value = "ctx-failed"
        workflow_map = [
            {
                "id": "create",
                "type": "context_create",
                "arguments": {"value_type": "content"},
                "successors": {},
                "data_inputs": {"initial-value": [None, None, "value"]},
                "data_outputs": {"context-id": []},
            }
        ]

        with self.assertRaisesRegex(ValueError, "workflow successor is not connected"):
            run_workflow_map(workflow_map, 0)

        delete_contexts.assert_called_once_with({"ctx-failed"})

    @patch("workflow_context_repository.delete_contexts")
    def test_cleanup_failure_does_not_replace_workflow_result(self, delete_contexts):
        from workflow_context_repository import WorkflowContextError

        delete_contexts.side_effect = WorkflowContextError("cleanup failed")
        workflow_map = [
            {
                "id": "output",
                "type": "output",
                "workflowPorts": [],
                "successors": {},
                "data_inputs": {},
                "data_outputs": {},
            }
        ]

        with self.assertLogs("aagent.workflow", level="ERROR"):
            self.assertEqual(run_workflow_map(workflow_map, 0), {})

    @patch("workflow_context_repository.delete_contexts")
    def test_cleanup_failure_does_not_replace_workflow_error(self, delete_contexts):
        from workflow_context_repository import WorkflowContextError

        delete_contexts.side_effect = WorkflowContextError("cleanup failed")
        workflow_map = [{"id": "broken", "type": "missing"}]

        with self.assertLogs("aagent.workflow", level="ERROR"):
            with self.assertRaisesRegex(ValueError, "unsupported workflow node type"):
                run_workflow_map(workflow_map, 0)

    @patch("workflow_parser.parse_workflow")
    @patch("workflow_parser._read_workflow")
    @patch("workflow_validator.validate_workflow")
    @patch("workflow_context_repository.delete_contexts")
    @patch("workflow_context_repository.create_context")
    def test_child_workflow_uses_and_cleans_independent_context_scope(
        self,
        create_context,
        delete_contexts,
        validate_workflow,
        read_workflow,
        parse_workflow,
    ):
        create_context.side_effect = ["ctx-parent", "ctx-child"]
        child_document = {"input_ports": [], "output_ports": []}
        read_workflow.return_value = child_document
        parse_workflow.return_value = [
            {
                "id": "child-input",
                "type": "input",
                "workflowPorts": [],
                "successors": {"next": 1},
                "data_inputs": {},
                "data_outputs": {},
            },
            {
                "id": "child-create",
                "type": "context_create",
                "arguments": {"value_type": "content"},
                "successors": {"next": 2},
                "data_inputs": {"initial-value": [None, None, "child"]},
                "data_outputs": {"context-id": []},
            },
            {
                "id": "child-output",
                "type": "output",
                "workflowPorts": [],
                "successors": {},
                "data_inputs": {},
                "data_outputs": {},
            },
        ]
        parent_map = [
            {
                "id": "parent-create",
                "type": "context_create",
                "arguments": {"value_type": "content"},
                "successors": {"next": 1},
                "data_inputs": {"initial-value": [None, None, "parent"]},
                "data_outputs": {"context-id": []},
            },
            {
                "id": "child-call",
                "type": "workflow",
                "arguments": {"workflow_name": "Child"},
                "input_ports": [],
                "output_ports": [],
                "successors": {"next": 2},
                "data_inputs": {},
                "data_outputs": {},
            },
            {
                "id": "parent-output",
                "type": "output",
                "workflowPorts": [],
                "successors": {},
                "data_inputs": {},
                "data_outputs": {},
            },
        ]

        self.assertEqual(run_workflow_map(parent_map, 0), {})

        parent_invocation = create_context.call_args_list[0].args[0]
        child_invocation = create_context.call_args_list[1].args[0]
        self.assertNotEqual(parent_invocation, child_invocation)
        self.assertEqual(
            [call.args[0] for call in delete_contexts.call_args_list],
            [{"ctx-child"}, {"ctx-parent"}],
        )
        validate_workflow.assert_called_once_with(child_document)

    def test_run_workflow_map_completes_foreach_in_one_call(self):
        input_items = ["first", "second", "third"]
        workflow_map = [
            {
                "id": "input",
                "type": "input",
                "successors": {"next": 1},
                "data_inputs": {},
                "data_outputs": {},
            },
            {
                "id": "foreach",
                "type": "foreach",
                "successors": {"item": 2, "next": 3},
                "data_inputs": {"list-in": [0, "list-out", input_items]},
                "data_outputs": {"item-out": [[2, "content-in"]]},
            },
            {
                "id": "body",
                "type": "construct_message",
                "successors": {"next": 1},
                "data_inputs": {"content-in": [1, "item-out", None]},
                "data_outputs": {"message-out": []},
            },
            {
                "id": "output",
                "type": "output",
                "workflowPorts": [],
                "successors": {},
                "data_inputs": {},
                "data_outputs": {},
            },
        ]

        self.assertEqual(run_workflow_map(workflow_map, 0), {})
        self.assertEqual(
            workflow_map[2]["data_inputs"]["content-in"],
            [1, "item-out", "third"],
        )
        self.assertEqual(len(workflow_map[2]["data_inputs"]["content-in"]), 3)
        self.assertEqual(input_items, ["first", "second", "third"])
        self.assertNotIn("_foreach_items", workflow_map[1])

    @patch("history_repository.get_recent_history")
    def test_history_node_returns_filtered_events(self, get_recent_history):
        get_recent_history.return_value = [
            {"event_type": "response", "payload": {"content": "first"}},
            {"event_type": "response", "payload": {"content": "second"}},
        ]
        workflow_map = [
            {
                "id": "history",
                "type": "history",
                "arguments": {"event_types": ["terminal", "response"], "limit": 2},
                "successors": {"next": 1},
                "data_inputs": {},
                "data_outputs": {"events": [[1, "workflow:events"]]},
            },
            {
                "id": "output",
                "type": "output",
                "workflowPorts": [
                    {"id": "workflow:events", "name": "events", "type": "event-list"}
                ],
                "successors": {},
                "data_inputs": {"workflow:events": [0, "events", None]},
                "data_outputs": {},
            },
        ]

        self.assertEqual(
            run_workflow_map(workflow_map, 0),
            {
                "events": [
                    {"event_type": "response", "payload": {"content": "first"}},
                    {"event_type": "response", "payload": {"content": "second"}},
                ]
            },
        )
        get_recent_history.assert_called_once_with(
            limit=2,
            event_types=["terminal", "response"],
        )

    def test_split_event_returns_type_and_payload(self):
        event = {
            "event_type": "response",
            "payload": {"content": "hello"},
        }
        workflow_map = [
            {
                "id": "split",
                "type": "split_event",
                "successors": {"next": 1},
                "data_inputs": {"event-in": [2, "item-out", event]},
                "data_outputs": {
                    "type-out": [[1, "workflow:type"]],
                    "payload-out": [[1, "workflow:payload"]],
                },
            },
            {
                "id": "output",
                "type": "output",
                "workflowPorts": [
                    {"id": "workflow:type", "name": "type", "type": "content"},
                    {"id": "workflow:payload", "name": "payload", "type": "content"},
                ],
                "successors": {},
                "data_inputs": {
                    "workflow:type": [0, "type-out", None],
                    "workflow:payload": [0, "payload-out", None],
                },
                "data_outputs": {},
            },
        ]

        self.assertEqual(workflow_split_event(0, workflow_map), 1)
        self.assertEqual(workflow_map[1]["data_inputs"]["workflow:type"][2], "response")
        self.assertEqual(
            workflow_map[1]["data_inputs"]["workflow:payload"][2],
            '{"content":"hello"}',
        )

    def test_deserialize_json_converts_content_and_list_content(self):
        workflow_map = [
            {
                "id": "deserialize",
                "type": "deserialize_json",
                "arguments": {
                    "outputs": [
                        {"key": "meta", "type": "content"},
                        {"key": "items", "type": "list-content"},
                    ]
                },
                "successors": {"next": 1},
                "data_inputs": {
                    "content-in": [2, "content-out", '{"meta":{"ok":true},"items":["plain",7,{"id":1},null]}']
                },
                "data_outputs": {
                    "meta": [[1, "meta-in"]],
                    "items": [[1, "items-in"]],
                },
            },
            {
                "data_inputs": {
                    "meta-in": [0, "meta", None],
                    "items-in": [0, "items", None],
                }
            },
        ]

        self.assertEqual(workflow_deserialize_json(0, workflow_map), 1)
        self.assertEqual(workflow_map[1]["data_inputs"]["meta-in"][2], '{"ok":true}')
        self.assertEqual(
            workflow_map[1]["data_inputs"]["items-in"][2],
            ["plain", "7", '{"id":1}', "null"],
        )

    def test_deserialize_json_does_not_propagate_partial_outputs(self):
        workflow_map = [
            {
                "id": "deserialize",
                "type": "deserialize_json",
                "arguments": {
                    "outputs": [
                        {"key": "first", "type": "content"},
                        {"key": "missing", "type": "content"},
                    ]
                },
                "successors": {"next": 1},
                "data_inputs": {"content-in": [2, "content-out", '{"first":"value"}']},
                "data_outputs": {"first": [[1, "first-in"]]},
            },
            {"data_inputs": {"first-in": [0, "first", None]}},
        ]

        with self.assertRaisesRegex(ValueError, "key is missing"):
            workflow_deserialize_json(0, workflow_map)
        self.assertIsNone(workflow_map[1]["data_inputs"]["first-in"][2])


if __name__ == "__main__":
    unittest.main()