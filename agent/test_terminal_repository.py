import unittest
from datetime import timezone
from unittest.mock import MagicMock, patch

from pymongo.errors import ServerSelectionTimeoutError

from terminal_repository import append_terminal_output, get_terminal_collection


class TerminalRepositoryTest(unittest.TestCase):
    @patch("terminal_repository.get_terminal_collection")
    def test_output_is_saved_as_plain_terminal_message(self, get_collection):
        collection = get_collection.return_value
        result = append_terminal_output("  原样保留\n第二行  ")
        document = collection.insert_one.call_args.args[0]
        self.assertEqual(document["content"], "  原样保留\n第二行  ")
        self.assertEqual(document["role"], "assistant")
        self.assertEqual(document["created_at"].tzinfo, timezone.utc)
        self.assertNotIn("event_type", document)
        self.assertEqual(result, collection.insert_one.return_value.inserted_id)

    @patch("terminal_repository.get_terminal_collection")
    def test_empty_or_non_string_output_is_rejected(self, get_collection):
        for content in (None, {}, "", "  "):
            with self.subTest(content=content), self.assertRaises(ValueError):
                append_terminal_output(content)
        get_collection.assert_not_called()

    @patch("terminal_repository.get_terminal_collection")
    def test_write_failure_propagates_to_tool_caller(self, get_collection):
        get_collection.return_value.insert_one.side_effect = ServerSelectionTimeoutError("offline")
        with self.assertRaises(ServerSelectionTimeoutError):
            append_terminal_output("hello")

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
