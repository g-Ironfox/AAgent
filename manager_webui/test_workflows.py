import unittest

from workflows import filter_invalid_connections, node_format_error


class WorkflowConnectionFilterTest(unittest.TestCase):
    def test_preserves_history_to_event_foreach_connection(self):
        nodes = [
            {
                "id": "history",
                "type": "history",
                "arguments": {"event_types": ["response"], "limit": 10},
            },
            {
                "id": "foreach",
                "type": "foreach",
                "arguments": {"item_type": "event"},
            },
        ]
        connection = {
            "id": "history-to-foreach",
            "fromId": "history",
            "fromPortId": "events",
            "toId": "foreach",
            "toPortId": "list-in",
            "type": "event-list",
        }

        _, connections = filter_invalid_connections(nodes, [connection], [], [])

        self.assertEqual(connections, [connection])

    def test_preserves_split_event_connections(self):
        nodes = [
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
        ]
        connections = [
            {"fromId": "input", "fromPortId": "workflow:event", "toId": "split", "toPortId": "event-in", "type": "event"},
            {"fromId": "split", "fromPortId": "type-out", "toId": "output", "toPortId": "workflow:type", "type": "content"},
            {"fromId": "split", "fromPortId": "payload-out", "toId": "output", "toPortId": "workflow:payload", "type": "content"},
        ]

        _, filtered = filter_invalid_connections(
            nodes,
            connections,
            [{"name": "event", "type": "event"}],
            [
                {"name": "type", "type": "content"},
                {"name": "payload", "type": "content"},
            ],
        )

        self.assertEqual(filtered, connections)

    def test_rejects_invalid_context_value_type(self):
        error = node_format_error(
            {
                "id": "context",
                "type": "context_create",
                "arguments": {"value_type": "number"},
            },
            0,
        )

        self.assertEqual(
            error,
            "nodes[0].arguments.value_type 必须是受支持的数据类型",
        )

    def test_preserves_construct_list_to_llm_messages_connection(self):
        nodes = [
            {
                "id": "messages",
                "type": "construct_list",
                "arguments": {
                    "item_type": "message",
                    "initial_value_count": 2,
                },
                "dataInputPorts": ["message-in-0", "message-in-1"],
            },
            {
                "id": "llm",
                "type": "llm",
                "arguments": {
                    "model": "model-id",
                    "think": False,
                    "tool_calls": False,
                    "tools": [],
                },
            },
        ]
        connection = {
            "id": "messages-to-llm",
            "fromId": "messages",
            "fromPortId": "list-out",
            "toId": "llm",
            "toPortId": "messages-in",
            "type": "list-message",
        }

        _, connections = filter_invalid_connections(nodes, [connection], [], [])

        self.assertEqual(connections, [connection])

    def test_preserves_context_connections_for_matching_value_type(self):
        for value_type in ("content", "message", "event", "list-content", "list-message", "event-list"):
            with self.subTest(value_type=value_type):
                nodes = [
                    {
                        "id": "create",
                        "type": "context_create",
                        "arguments": {"value_type": value_type},
                    },
                    {
                        "id": "write",
                        "type": "context_write",
                        "arguments": {"value_type": value_type},
                    },
                    {
                        "id": "read",
                        "type": "context_read",
                        "arguments": {"value_type": value_type},
                    },
                    {
                        "id": "output",
                        "type": "output",
                        "workflowPorts": [
                            {"id": "workflow:value", "name": "value", "type": value_type}
                        ],
                    },
                ]
                connections = [
                    {"fromId": "create", "fromPortId": "context-id", "toId": "write", "toPortId": "context-id", "type": "content"},
                    {"fromId": "write", "fromPortId": "context-id", "toId": "read", "toPortId": "context-id", "type": "content"},
                    {"fromId": "write", "fromPortId": "value-out", "toId": "output", "toPortId": "workflow:value", "type": value_type},
                ]

                _, filtered = filter_invalid_connections(
                    nodes,
                    connections,
                    [],
                    [{"name": "value", "type": value_type}],
                )

                self.assertEqual(filtered, connections)

    def test_drops_context_value_connection_after_type_change(self):
        nodes = [
            {
                "id": "write",
                "type": "context_write",
                "arguments": {"value_type": "message"},
            },
            {
                "id": "output",
                "type": "output",
                "workflowPorts": [
                    {"id": "workflow:value", "name": "value", "type": "content"}
                ],
            },
        ]
        connection = {
            "fromId": "write",
            "fromPortId": "value-out",
            "toId": "output",
            "toPortId": "workflow:value",
            "type": "content",
        }

        _, connections = filter_invalid_connections(
            nodes,
            [connection],
            [],
            [{"name": "value", "type": "content"}],
        )

        self.assertEqual(connections, [])


if __name__ == "__main__":
    unittest.main()