import unittest
from unittest.mock import patch

from workflow_parser import parse_workflow
from workflow_nodes import run_workflow_map
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
    def test_validator_and_parser_accept_history_node(self):
        workflow = {
            "input_ports": [],
            "output_ports": [{"name": "events", "type": "list-content"}],
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
                        {"id": "workflow:events", "name": "events", "type": "list-content"}
                    ],
                },
            ],
            "connections": [
                {"fromId": "input", "fromPortId": "control-out", "toId": "history", "toPortId": "control-in", "type": "control"},
                {"fromId": "history", "fromPortId": "control-out", "toId": "output", "toPortId": "control-in", "type": "control"},
                {"fromId": "history", "fromPortId": "events", "toId": "output", "toPortId": "workflow:events", "type": "list-content"},
            ],
        }

        validate_workflow(workflow)
        parsed = parse_workflow(workflow)

        self.assertEqual(
            parsed[1]["arguments"],
            {"event_types": ["terminal", "response"], "limit": 5},
        )
        self.assertEqual(parsed[1]["data_outputs"]["events"], [[2, "workflow:events"]])

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
    def test_history_node_returns_filtered_events_as_json_content(self, get_recent_history):
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
                    {"id": "workflow:events", "name": "events", "type": "list-content"}
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
                    '{"event_type": "response", "payload": {"content": "first"}}',
                    '{"event_type": "response", "payload": {"content": "second"}}',
                ]
            },
        )
        get_recent_history.assert_called_once_with(
            limit=2,
            event_types=["terminal", "response"],
        )


if __name__ == "__main__":
    unittest.main()