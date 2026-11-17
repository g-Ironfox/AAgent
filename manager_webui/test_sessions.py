import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock

from fastapi.responses import JSONResponse

from sessions import SessionValueRequest, create_sessions_router


class SessionApiTest(unittest.TestCase):
    def setUp(self):
        self.collection = MagicMock()
        router = create_sessions_router(self.collection)
        self.routes = {(method, route.path): route.endpoint for route in router.routes for method in route.methods}
        self.session_id = "ses_" + "a" * 32
        self.updated = datetime(2026, 1, 1, tzinfo=timezone.utc)

    def test_create_rejects_invalid_value(self):
        response = self.routes["POST", "/api/sessions"](SessionValueRequest(value_type="event", value={}))
        self.assertIsInstance(response, JSONResponse)
        self.assertEqual(response.status_code, 400)
        self.collection.insert_one.assert_not_called()

    def test_create_accepts_only_string_map_content_entries(self):
        response = self.routes["POST", "/api/sessions"](
            SessionValueRequest(value_type="map-content", value={"ready": "ok"})
        )
        self.assertNotIsInstance(response, JSONResponse)
        for value in ({"": "empty"}, {"ready": 1}, ["ready"]):
            with self.subTest(value=value):
                response = self.routes["POST", "/api/sessions"](
                    SessionValueRequest(value_type="map-content", value=value)
                )
                self.assertIsInstance(response, JSONResponse)
                self.assertEqual(response.status_code, 400)

    def test_numeric_sessions_keep_their_type_and_reject_invalid_numbers(self):
        for value in (0, -12, 1.25):
            with self.subTest(value=value):
                created = self.routes["POST", "/api/sessions"](
                    SessionValueRequest(value_type="number", value=value)
                )
                self.assertEqual(created["value"], value)
                self.assertIs(type(created["value"]), type(value))
                self.collection.find_one_and_update.return_value = {
                    "_id": self.session_id, "value_type": "number", "value": value,
                    "created_at": self.updated, "updated_at": self.updated,
                }
                updated = self.routes["PUT", "/api/sessions/{session_id}"](
                    self.session_id, SessionValueRequest(value_type="number", value=value, updated_at=self.updated)
                )
                self.assertEqual(updated["value"], value)
                self.assertIs(type(updated["value"]), type(value))
        for value in (True, False, None, "12", [], {}, float("nan"), float("inf")):
            with self.subTest(value=value):
                response = self.routes["POST", "/api/sessions"](
                    SessionValueRequest(value_type="number", value=value)
                )
                self.assertIsInstance(response, JSONResponse)
                self.assertEqual(response.status_code, 400)

    def test_update_detects_concurrent_write(self):
        self.collection.find_one_and_update.return_value = None
        self.collection.find_one.return_value = {"_id": self.session_id}
        response = self.routes["PUT", "/api/sessions/{session_id}"](
            self.session_id, SessionValueRequest(value_type="content", value="new", updated_at=self.updated)
        )
        self.assertEqual(response.status_code, 409)
        expected_filter = {"_id": self.session_id, "value_type": "content", "updated_at": self.updated}
        self.assertEqual(self.collection.find_one_and_update.call_args.args[0], expected_filter)

    def test_list_paginates_with_timestamp_and_id(self):
        later_id = "ses_" + "b" * 32
        documents = [
            {"_id": later_id, "value_type": "content", "created_at": self.updated, "updated_at": self.updated},
            {"_id": self.session_id, "value_type": "content", "created_at": self.updated, "updated_at": self.updated},
        ]
        self.collection.find.return_value.sort.return_value.limit.return_value = documents
        list_sessions = self.routes["GET", "/api/sessions"]
        first = list_sessions(limit=1, cursor=None, q="ses_")
        self.assertEqual([item["id"] for item in first["items"]], [later_id])
        self.assertIsNotNone(first["next_cursor"])
        self.assertEqual(self.collection.find.call_args.args[0]["_id"], {"$regex": "^ses_"})
        list_sessions(limit=1, cursor=first["next_cursor"], q="")
        self.assertEqual(self.collection.find.call_args.args[0]["$or"][1]["_id"], {"$lt": later_id})


if __name__ == "__main__":
    unittest.main()