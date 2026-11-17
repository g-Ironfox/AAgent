import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from workflow_session_repository import (
    WorkflowSessionError,
    create_session,
    read_session,
    write_session,
)


VALUES = {
    "content": "hello",
    "message": {"role": "user", "content": "hello"},
    "list-content": ["hello"],
    "list-message": [{"role": "assistant", "content": "hello"}],
    "map-content": {"done": "finished"},
}


class WorkflowSessionRepositoryTest(unittest.TestCase):
    @patch("workflow_session_repository.get_session_collection")
    def test_supported_types_create_read_and_write_without_ttl(self, get_collection):
        collection = get_collection.return_value
        collection.update_one.return_value.matched_count = 1
        for value_type, value in VALUES.items():
            with self.subTest(value_type=value_type):
                created = create_session(value_type, value)
                document = collection.insert_one.call_args.args[0]
                self.assertEqual(document["value"], value)
                self.assertEqual(set(document), {"_id", "value_type", "value", "created_at", "updated_at"})
                self.assertEqual(created["value_type"], value_type)
                collection.find_one.return_value = document
                self.assertEqual(read_session(created["id"], value_type), value)
                write_session(created["id"], value_type, value)
                self.assertEqual(collection.update_one.call_args.args[1]["$set"]["value"], value)

    @patch("workflow_session_repository.get_session_collection")
    def test_write_retries_after_concurrent_update(self, get_collection):
        collection = get_collection.return_value
        session_id = "ses_" + "a" * 32
        first = datetime(2026, 1, 1, tzinfo=timezone.utc)
        second = datetime(2026, 1, 2, tzinfo=timezone.utc)
        collection.find_one.side_effect = [{"updated_at": first}, {"updated_at": second}]
        collection.update_one.side_effect = [MagicMock(matched_count=0), MagicMock(matched_count=1)]

        write_session(session_id, "content", "new")

        self.assertEqual(collection.update_one.call_count, 2)
        self.assertEqual(collection.update_one.call_args.args[0]["updated_at"], second)

    @patch("workflow_session_repository.get_session_collection")
    def test_missing_and_invalid_values_are_rejected(self, get_collection):
        get_collection.return_value.find_one.return_value = None
        with self.assertRaisesRegex(WorkflowSessionError, "不存在"):
            read_session("ses_" + "a" * 32, "content")
        with self.assertRaisesRegex(WorkflowSessionError, "ID 输入无效"):
            read_session("ses_wrong", "content")
        for value_type, value in [("content", 3), ("event", {}), ("message", {"role": "wrong", "content": "x"}), ("list-event", [{}]), ("map-content", {"": "empty"}), ("map-content", {"key": 1})]:
            with self.subTest(value_type=value_type, value=value), self.assertRaises(WorkflowSessionError):
                create_session(value_type, value)
        with patch("workflow_session_repository._max_value_bytes", return_value=3):
            with self.assertRaisesRegex(WorkflowSessionError, "过大"):
                create_session("content", "hello")


if __name__ == "__main__":
    unittest.main()