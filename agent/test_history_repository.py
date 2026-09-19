import unittest
from unittest.mock import MagicMock, patch

from history_repository import get_recent_history


class HistoryRepositoryTest(unittest.TestCase):
    @patch("history_repository.get_history_collection")
    def test_event_type_filter_does_not_leak_between_calls(self, get_collection):
        collection = MagicMock()
        cursor = collection.find.return_value
        cursor.sort.return_value = cursor
        cursor.limit.return_value = []
        get_collection.return_value = collection

        get_recent_history(limit=2, event_types=["terminal", "response"])
        get_recent_history(limit=3)

        self.assertEqual(
            collection.find.call_args_list[0].args[0],
            {"event_type": {"$in": ["terminal", "response"]}},
        )
        self.assertEqual(collection.find.call_args_list[1].args[0], {})


if __name__ == "__main__":
    unittest.main()