import unittest
from datetime import timezone
from unittest.mock import MagicMock, patch

from pymongo.errors import ServerSelectionTimeoutError

from terminal_repository import append_terminal_output, get_terminal_collection, read_terminal_input, terminal_process_context
from workflow_nodes import nodes_map


class TerminalRepositoryTest(unittest.TestCase):
    @patch("terminal_repository.get_terminal_collection")
    def test_output_is_saved_as_plain_terminal_message(self, get_collection):
        collection = get_collection.return_value
        result = append_terminal_output("  原样保留\n第二行  ", "terminal-1")
        document = collection.insert_one.call_args.args[0]
        self.assertEqual(document["content"], "  原样保留\n第二行  ")
        self.assertEqual(document["role"], "assistant")
        self.assertEqual(document["created_at"].tzinfo, timezone.utc)
        self.assertNotIn("event_type", document)
        self.assertEqual(document["terminal_process_id"], "terminal-1")
        self.assertEqual(result, collection.insert_one.return_value.inserted_id)

    @patch("terminal_repository.get_terminal_collection")
    def test_reads_all_user_input_in_database_order_without_consuming(self, get_collection):
        cursor = get_collection.return_value.find.return_value
        cursor.sort.return_value = [{"content": "first"}, {"content": "second\nline"}]
        self.assertEqual(read_terminal_input("terminal-1"), ["first", "second\nline"])
        get_collection.return_value.find.assert_called_once_with(
            {"terminal_process_id": "terminal-1", "role": "user"}, {"content": 1}
        )
        cursor.sort.assert_called_once_with([("created_at", 1), ("_id", 1)])

    @patch("terminal_repository.get_terminal_collection")
    def test_terminal_input_requires_valid_terminal_id(self, get_collection):
        for terminal_id in (None, "", "  ", 42):
            with self.subTest(terminal_id=terminal_id), self.assertRaises(ValueError):
                read_terminal_input(terminal_id)
        get_collection.assert_not_called()

    @patch("terminal_repository.read_terminal_input", return_value=["one", "two"])
    def test_read_terminal_input_node_emits_list_content(self, read_input):
        node = {"id": "read", "type": "read_terminal_input",
                "successors": {"next": 1},
                "data_outputs": {"list-out": [[1, "list-in"]]}}
        target = {"data_inputs": {"list-in": [None, "list-content", None]}}
        with terminal_process_context("terminal-1"):
            self.assertEqual(nodes_map["read_terminal_input"](0, [node, target]), 1)
        read_input.assert_called_once_with("terminal-1")
        self.assertEqual(target["data_inputs"]["list-in"][2], ["one", "two"])

    @patch("terminal_repository.get_terminal_collection")
    def test_empty_or_non_string_output_is_rejected(self, get_collection):
        for content in (None, {}, "", "  "):
            with self.subTest(content=content), self.assertRaises(ValueError):
                append_terminal_output(content, "terminal-1")
        get_collection.assert_not_called()

    @patch("terminal_repository.get_terminal_collection")
    def test_write_failure_propagates_to_tool_caller(self, get_collection):
        get_collection.return_value.insert_one.side_effect = ServerSelectionTimeoutError("offline")
        with self.assertRaises(ServerSelectionTimeoutError):
            append_terminal_output("hello", "terminal-1")

    @patch("terminal_repository.get_terminal_collection")
    def test_output_requires_a_process_terminal(self, get_collection):
        with self.assertRaises(TypeError):
            append_terminal_output("hello")
        for terminal_id in (None, "", "  ", 42):
            with self.subTest(terminal_id=terminal_id), self.assertRaises(ValueError):
                append_terminal_output("hello", terminal_id)
        get_collection.assert_not_called()

    def test_collection_is_configurable_and_client_is_reused(self):
        environment = {
            "MONGO_HOST": "database.test", "MONGO_PORT": "27018", "MONGO_USER": "agent",
            "MONGO_PASS": "test", "MONGO_DATABASE": "custom", "MONGO_TERMINAL_COLLECTION": "messages",
        }
        with patch.dict("os.environ", environment), patch("terminal_repository.MongoClient") as client, \
             patch("terminal_repository._client", None), patch("terminal_repository._collection", None):
            collection = get_terminal_collection()
            self.assertIs(get_terminal_collection(), collection)
            client.assert_called_once_with(
                host="database.test", port=27018, serverSelectionTimeoutMS=5000, tz_aware=True,
                username="agent", password="test", authSource="admin",
            )
            self.assertIs(collection, client.return_value["custom"]["messages"])


if __name__ == "__main__":
    unittest.main()
