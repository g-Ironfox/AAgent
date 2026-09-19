import unittest

from workflows import filter_invalid_connections


class WorkflowConnectionFilterTest(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()