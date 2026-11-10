import json
import unittest
from unittest.mock import MagicMock

from bson import ObjectId
from pydantic import ValidationError
from pymongo.errors import DuplicateKeyError

from event_bindings import EventBindingRequest, create_event_bindings_router
from file_store import FileStore, FileStoreUnavailableError
from test_file_store import FakeCollection, FakeWorkspaceCollection


def workflow_content(**changes):
    return json.dumps({
        "schema_version": "2.0", "name": "example", "nodes": [], "connections": [],
        "input_ports": [{"name": "content", "type": "content"}], "output_ports": [],
        **changes,
    })


class EventBindingTest(unittest.TestCase):
    def setUp(self):
        self.store = FileStore(FakeCollection(), FakeWorkspaceCollection())
        self.bindings = MagicMock()
        self.binding_id = ObjectId()
        self.bindings.insert_one.return_value.inserted_id = self.binding_id
        router = create_event_bindings_router(self.bindings, self.store)
        routes = {(method, route.path): route.endpoint for route in router.routes for method in route.methods}
        self.options = routes["GET", "/api/event-bindings/workflow-options"]
        self.create = routes["POST", "/api/event-bindings"]
        self.update = routes["PUT", "/api/event-bindings/{binding_id}"]
        self.delete = routes["DELETE", "/api/event-bindings/{binding_id}"]

    def test_options_use_workspace_file_ids_names_and_contract(self):
        valid = self.store.create_file("workflow.txt", workflow_content())
        self.store.create_file("notes.json", "not JSON")
        self.store.create_file("array.json", "[]")
        self.store.create_file("old.json", workflow_content(schema_version="1.7"))
        self.store.create_file("bad-ports.json", workflow_content(input_ports=[None]))
        self.store.create_file("bad-nodes.json", workflow_content(nodes={}))
        self.assertEqual(self.options()["items"], [{
            "file_id": valid["file_id"], "name": "workflow.txt", "workflow_name": "example",
            "input_ports": [{"name": "content", "type": "content"}], "output_ports": [],
        }])

    def test_create_stores_stable_file_reference(self):
        file = self.store.create_file("flow.json", workflow_content())
        response = self.create(EventBindingRequest(
            event_type=" TERMINAL ", workflow_file_id=file["file_id"], enabled=False,
        ))
        self.assertEqual(response["workflow_file_id"], file["file_id"])
        self.bindings.insert_one.assert_called_once_with({
            "event_type": "terminal", "workflow_file_id": file["file_id"],
            "workflow_file_name": "flow.json", "enabled": False,
        })

    def test_missing_or_invalid_file_cannot_be_bound(self):
        bad = self.store.create_file("bad.json", "null")
        for file_id, status in (("missing", 404), (bad["file_id"], 400)):
            with self.subTest(file_id=file_id):
                response = self.create(EventBindingRequest(event_type="terminal", workflow_file_id=file_id))
                self.assertEqual(response.status_code, status)
        self.bindings.insert_one.assert_not_called()

    def test_update_revalidates_latest_content_and_removes_legacy_selector(self):
        file = self.store.create_file("flow.json", workflow_content())
        file = self.store.update_file(file["file_id"], "renamed.json", file["content"], file["revision"])
        self.bindings.find_one_and_update.return_value = {"_id": self.binding_id, "workflow_file_id": file["file_id"]}
        response = self.update(str(self.binding_id), EventBindingRequest(
            event_type="terminal", workflow_file_id=file["file_id"],
        ))
        self.assertEqual(response["workflow_file_id"], file["file_id"])
        update = self.bindings.find_one_and_update.call_args.args[1]
        self.assertEqual(update["$set"]["workflow_file_name"], "renamed.json")
        self.assertEqual(update["$unset"], {"workflow_name": "", "workflow_id": ""})
        self.store.update_file(file["file_id"], file["name"], "broken", file["revision"])
        self.bindings.find_one_and_update.reset_mock()
        response = self.update(str(self.binding_id), EventBindingRequest(
            event_type="terminal", workflow_file_id=file["file_id"],
        ))
        self.assertEqual(response.status_code, 400)
        self.bindings.find_one_and_update.assert_not_called()

    def test_invalid_binding_id_returns_400_for_update_and_delete(self):
        self.assertEqual(self.delete("bad").status_code, 400)
        self.assertEqual(self.update("bad", EventBindingRequest(
            event_type="terminal", workflow_file_id="file-1",
        )).status_code, 400)

    def test_duplicate_event_and_invalid_event_type(self):
        file = self.store.create_file("flow.json", workflow_content())
        self.bindings.insert_one.side_effect = DuplicateKeyError("duplicate")
        self.assertEqual(self.create(EventBindingRequest(
            event_type="terminal", workflow_file_id=file["file_id"],
        )).status_code, 409)
        self.bindings.insert_one.reset_mock()
        self.assertEqual(self.create(EventBindingRequest(
            event_type="bad type", workflow_file_id=file["file_id"],
        )).status_code, 400)
        self.bindings.insert_one.assert_not_called()

    def test_legacy_name_only_requests_require_file_selection(self):
        with self.assertRaises(ValidationError):
            EventBindingRequest(event_type="terminal", workflow_name="old")

    def test_store_outage_is_not_an_empty_option_list(self):
        store = MagicMock()
        store.list_files.side_effect = FileStoreUnavailableError("unavailable")
        router = create_event_bindings_router(self.bindings, store)
        endpoint = next(route.endpoint for route in router.routes if route.path.endswith("workflow-options"))
        with self.assertRaises(FileStoreUnavailableError):
            endpoint()


if __name__ == "__main__":
    unittest.main()
