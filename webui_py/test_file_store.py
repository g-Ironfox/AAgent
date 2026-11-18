import unittest

from pymongo.errors import DuplicateKeyError, ServerSelectionTimeoutError

from files import FileRequest, create_files_router
from file_store import (
    FileConflictError, FileMissingError, FileNameConflictError, FileStore, FileStoreUnavailableError,
)


class FakeCursor(list):
    def sort(self, key, direction):
        return FakeCursor(sorted(self, key=lambda event: event[key], reverse=direction < 0))

    def limit(self, count):
        return FakeCursor(self[:count])


class FakeCollection:
    def __init__(self, fail=False):
        self.documents = []
        self.fail = fail

    def _check(self):
        if self.fail:
            raise ServerSelectionTimeoutError("MongoDB unavailable")

    def create_index(self, *_args, **_kwargs):
        self._check()

    def find(self, query, projection=None):
        self._check()
        events = [doc for doc in self.documents if "type" in doc]
        if "type" in query and isinstance(query["type"], str):
            events = [doc for doc in events if doc["type"] == query["type"]]
        elif "type" in query and "$in" in query["type"]:
            events = [doc for doc in events if doc["type"] in query["type"]["$in"]]
        if "seq" in query:
            sequence = query["seq"]
            if isinstance(sequence, dict):
                events = [doc for doc in events if doc["seq"] < sequence["$lt"]]
            else:
                events = [doc for doc in events if doc["seq"] == sequence]
        if "file_id" in query:
            events = [doc for doc in events if doc["file_id"] == query["file_id"]]
        if "data.files.file_id" in query:
            events = [doc for doc in events if any(
                item["file_id"] == query["data.files.file_id"] for item in doc["data"]["files"]
            )]
        if projection:
            projected = []
            for event in events:
                item = {
                    key: event[key] for key in event
                    if projection.get(key) and key != "data"
                }
                data_fields = [key.split(".", 1)[1] for key, include in projection.items()
                               if include and key.startswith("data.")]
                if data_fields:
                    item["data"] = {
                        key: event["data"][key] for key in data_fields if key in event.get("data", {})
                    }
                projected.append(item)
            events = projected
        return FakeCursor(events)

    def find_one_and_update(self, query, update, upsert=False, return_document=None):
        self._check()
        document = next((doc for doc in self.documents if doc.get("_id") == query["_id"]), None)
        if document is None:
            if not upsert:
                return None
            document = {"_id": query["_id"], **update.get("$setOnInsert", {})}
            self.documents.append(document)
        if "$inc" in update:
            for key, amount in update["$inc"].items():
                document[key] = document.get(key, 0) + amount
        return dict(document)

    def insert_one(self, document):
        self._check()
        self.documents.append(dict(document))


class FakeWorkspaceCollection:
    def __init__(self):
        self.documents = []
        self.indexes = []
        self.reject_name_once = None

    def create_index(self, keys, **options):
        self.indexes.append((keys, options))

    def find_one(self, query, projection=None, sort=None):
        docs = [doc for doc in self.documents if all(
            (key not in doc if isinstance(value, dict) and value.get("$exists") is False
             else key in doc if isinstance(value, dict) and value.get("$exists") is True
             else doc.get(key) == value)
            for key, value in query.items()
        )]
        if sort:
            key, direction = sort[0]
            docs.sort(key=lambda doc: doc.get(key, 0), reverse=direction < 0)
        if not docs:
            return None
        result = dict(docs[0])
        if projection:
            if all(value == 0 for value in projection.values()):
                result = {key: value for key, value in result.items() if key not in projection}
            else:
                result = {key: result[key] for key, value in projection.items() if value and key in result}
        return result

    def find(self, query, projection=None):
        documents = [dict(doc) for doc in self.documents if doc.get("generation") == query["generation"]]
        if projection and projection.get("content") == 0:
            for document in documents:
                document.pop("content", None)
        return FakeCursor(documents)

    def insert_one(self, document):
        if any(doc.get("_id") == document["_id"] for doc in self.documents):
            raise RuntimeError("duplicate key")
        if document.get("name") == self.reject_name_once:
            self.reject_name_once = None
            raise DuplicateKeyError(
                "duplicate workspace filename", details={"keyPattern": {"generation": 1, "name": 1}}
            )
        self._assert_unique_name(document)
        self.documents.append(dict(document))

    def replace_one(self, query, document, upsert=False):
        for index, current in enumerate(self.documents):
            if current.get("_id") == query["_id"]:
                self._assert_unique_name(document, exclude_id=query["_id"])
                self.documents[index] = dict(document)
                return
        if upsert:
            self.documents.append(dict(document))

    def _assert_unique_name(self, document, exclude_id=None):
        if not document.get("file_id"):
            return
        if any(
            current.get("file_id")
            and current.get("_id") != exclude_id
            and current.get("generation") == document.get("generation")
            and current.get("name") == document.get("name")
            for current in self.documents
        ):
            raise DuplicateKeyError(
                "duplicate workspace filename", details={"keyPattern": {"generation": 1, "name": 1}}
            )

    def delete_one(self, query):
        self.documents = [doc for doc in self.documents if doc.get("_id") != query["_id"]]

    def delete_many(self, query):
        generation = query["generation"]
        if isinstance(generation, dict):
            self.documents = [doc for doc in self.documents if doc.get("generation") == generation["$ne"]]
        else:
            self.documents = [doc for doc in self.documents if doc.get("generation") != generation]


class FileStoreTests(unittest.TestCase):
    def setUp(self):
        self.collection = FakeCollection()
        self.workspace = FakeWorkspaceCollection()
        self.store = FileStore(self.collection, self.workspace)

    def test_mutations_persist_directly_to_workspace_collection(self):
        created = self.store.create_file("First", "initial")
        updated = self.store.update_file(created["file_id"], "Renamed", "body", created["revision"])
        pinned = self.store.set_pinned(updated["file_id"], True, updated["revision"])

        replayed = FileStore(self.collection, self.workspace)

        self.assertEqual(replayed.get_file(created["file_id"]), pinned)
        self.assertEqual(replayed.revision, 0)
        self.assertEqual([item["type"] for item in self.collection.documents if "type" in item], [])

        replayed.delete_file(created["file_id"], pinned["revision"])
        self.assertEqual(replayed.list_files(), [])
        self.assertEqual(FileStore(self.collection, self.workspace).list_files(), [])

    def test_file_names_are_unique_case_sensitively_for_create_and_rename(self):
        lower = self.store.create_file("child.flow")
        upper = self.store.create_file("Child.flow")
        self.assertNotEqual(lower["file_id"], upper["file_id"])

        with self.assertRaises(FileNameConflictError):
            self.store.create_file("child.flow")
        with self.assertRaises(FileNameConflictError):
            self.store.update_file(upper["file_id"], "child.flow", "", upper["revision"])

        unchanged = self.store.update_file(lower["file_id"], "child.flow", "updated", lower["revision"])
        renamed = self.store.update_file(upper["file_id"], "CHILD.flow", "", upper["revision"])
        self.assertEqual(unchanged["name"], "child.flow")
        self.assertEqual(renamed["name"], "CHILD.flow")

    def test_file_name_index_is_unique_and_uses_simple_collation(self):
        keys, options = self.workspace.indexes[0]
        self.assertEqual(keys, [("generation", 1), ("name", 1)])
        self.assertTrue(options["unique"])
        self.assertEqual(options["collation"].document["locale"], "simple")

    def test_database_unique_index_conflict_maps_to_file_name_conflict(self):
        self.workspace.reject_name_once = "raced.flow"

        with self.assertRaises(FileNameConflictError):
            self.store.create_file("raced.flow")

    def test_file_name_conflicts_map_to_http_409(self):
        routes = {route.path: route for route in create_files_router(self.store).routes}
        create = routes["/api/files"].endpoint
        update = routes["/api/files/{file_id}"].endpoint
        created = create(FileRequest(name="child.flow"))

        self.assertEqual(create(FileRequest(name="child.flow")).status_code, 409)
        create(FileRequest(name="other.flow"))
        conflict = update(
            created["file_id"],
            FileRequest(name="other.flow", content="", revision=created["revision"]),
        )
        self.assertEqual(conflict.status_code, 409)

    def test_stale_revision_is_rejected_without_writing(self):
        created = self.store.create_file("First")
        updated = self.store.update_file(created["file_id"], "Second", "", created["revision"])

        with self.assertRaises(FileConflictError):
            self.store.update_file(created["file_id"], "Stale", "", created["revision"])

        self.assertEqual(self.store.get_file(created["file_id"])["revision"], updated["revision"])
        self.assertEqual(len([doc for doc in self.collection.documents if "type" in doc]), 0)

    def test_missing_file_is_rejected(self):
        with self.assertRaises(FileMissingError):
            self.store.get_file("missing")

    def test_mongo_unavailable_is_reported_without_blocking_construction(self):
        store = FileStore(FakeCollection(fail=True), FakeWorkspaceCollection())

        with self.assertRaises(FileStoreUnavailableError):
            store.list_files()

    def test_file_mutation_does_not_write_event_records(self):
        self.store.create_file("First")

        self.assertEqual(len(self.collection.documents), 1)
        self.assertIn("next_seq", self.collection.documents[0])
        self.assertFalse(any("type" in document for document in self.collection.documents))

    def test_events_can_be_filtered_and_paginated_by_sequence(self):
        first = self.store.create_checkpoint("First")
        second = self.store.create_checkpoint("Second")
        restored = self.store.restore_checkpoint(first["seq"])

        self.assertEqual([event["seq"] for event in self.store.list_events(limit=2)], [restored["seq"], second["seq"]])
        self.assertEqual(
            [event["seq"] for event in self.store.list_events(before_seq=restored["seq"], file_id="workspace")],
            [second["seq"], first["seq"]],
        )
        self.assertEqual(self.store.list_events(before_seq=second["seq"], file_id="other"), [])

    def test_checkpoint_keeps_an_immutable_workspace_diff(self):
        created = self.store.create_file("First", "before checkpoint")

        checkpoint = self.store.create_checkpoint("Before refactor")
        self.store.update_file(created["file_id"], "First", "after checkpoint", created["revision"])
        replayed = FileStore(self.collection, self.workspace)

        self.assertEqual(checkpoint["type"], "workspace.checkpoint")
        self.assertIsNone(checkpoint["data"]["parent_seq"])
        self.assertEqual(checkpoint["data"]["files"][0]["content"], "before checkpoint")
        self.assertEqual(replayed.get_file(created["file_id"])["content"], "after checkpoint")
        self.assertEqual(replayed._checkpoint_state(checkpoint["seq"])[0]["content"], "before checkpoint")
        diff = replayed.checkpoint_diff(checkpoint["seq"])["changes"][0]
        self.assertIsNone(diff["before_content"])
        self.assertEqual(diff["after_content"], "before checkpoint")
        self.assertEqual(diff["after_changed_lines"], [0])
        self.assertEqual(replayed.list_checkpoints()[0]["seq"], checkpoint["seq"])
        self.assertNotIn("files", replayed.list_checkpoints()[0]["data"])
        self.assertEqual(replayed.list_checkpoints(file_id=created["file_id"])[0]["seq"], checkpoint["seq"])
        self.assertEqual(replayed.revision, checkpoint["seq"])

    def test_checkpoint_listing_and_tree_do_not_add_a_virtual_root(self):
        first = self.store.create_checkpoint("First")

        page = self.store.list_checkpoints(limit=2)
        final_page = self.store.list_checkpoints(before_seq=first["seq"], limit=2)

        self.assertEqual([item["seq"] for item in page], [first["seq"]])
        self.assertEqual(final_page, [])
        self.assertEqual(self.store.list_checkpoints(file_id="some-file"), [])
        tree = self.store.checkpoint_tree()
        self.assertEqual([item["seq"] for item in tree["items"]], [first["seq"]])
        self.assertIsNone(tree["items"][0]["data"]["parent_seq"])
        self.assertEqual(tree["head_seq"], first["seq"])
        self.assertEqual(
            [event["type"] for event in self.store.list_events(limit=10)],
            ["workspace.checkpoint"],
        )

    def test_first_checkpoint_without_existing_head_becomes_root_and_head(self):
        file = self.store.create_file("Before replay", "current workspace")

        self.assertEqual(self.store.checkpoint_tree(), {"items": [], "head_seq": None})

        checkpoint = self.store.create_checkpoint("Root")
        tree = self.store.checkpoint_tree()

        self.assertIsNone(checkpoint["data"]["parent_seq"])
        self.assertEqual(tree["head_seq"], checkpoint["seq"])
        self.assertEqual(tree["items"][0]["seq"], checkpoint["seq"])
        self.assertEqual(self.store._checkpoint_state(checkpoint["seq"])[0]["content"], "current workspace")
        self.assertEqual(self.store.get_file(file["file_id"])["content"], "current workspace")

    def test_genesis_checkpoint_restore_is_visible_after_reopening_store(self):
        self.store.create_file("Seeded file", "from replayed history")

        restored = self.store.restore_checkpoint(0)
        replayed = FileStore(self.collection, self.workspace)

        self.assertEqual(restored["data"]["checkpoint_seq"], 0)
        self.assertEqual(self.store.list_files(), [])
        self.assertEqual(replayed.list_files(), [])
        self.assertEqual(replayed.revision, restored["seq"])

    def test_restore_checkpoint_replaces_workspace_and_persists_event(self):
        original = self.store.create_file("Original", "before")
        checkpoint = self.store.create_checkpoint("Known good")
        self.store.update_file(original["file_id"], "Changed", "after", original["revision"])
        extra = self.store.create_file("Extra", "remove me")

        restored = self.store.restore_checkpoint(checkpoint["seq"])
        files = self.store.list_files()
        replayed = FileStore(self.collection, self.workspace)

        self.assertEqual(restored["type"], "workspace.restore")
        self.assertEqual(restored["data"]["checkpoint_seq"], checkpoint["seq"])
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0]["file_id"], original["file_id"])
        self.assertEqual(files[0]["name"], "Original")
        self.assertEqual(self.store.get_file(original["file_id"])["content"], "before")
        self.assertGreater(files[0]["revision"], extra["revision"])
        self.assertEqual(replayed.list_files(), files)

    def test_restore_checkpoint_can_restore_empty_workspace(self):
        checkpoint = self.store.create_checkpoint("Empty")
        self.store.create_file("Later")

        self.store.restore_checkpoint(checkpoint["seq"])

        self.assertEqual(self.store.list_files(), [])

    def test_restore_rejects_checkpoint_with_duplicate_exact_names(self):
        self.store.create_file("child.flow")
        checkpoint = self.store.create_checkpoint("Legacy duplicate")
        event = next(item for item in self.collection.documents if item.get("seq") == checkpoint["seq"])
        duplicate = dict(event["data"]["files"][0])
        duplicate["file_id"] = "duplicate-file-id"
        event["data"]["files"].append(duplicate)

        with self.assertRaises(FileNameConflictError):
            self.store.restore_checkpoint(checkpoint["seq"])

    def test_checkpoint_tree_branches_after_restore_and_stores_full_snapshots(self):
        file = self.store.create_file("Notes", "one\ntwo\nthree\n")
        first = self.store.create_checkpoint("First")
        self.store.update_file(file["file_id"], "Notes", "one\ntwo changed\nthree\n", file["revision"])
        second = self.store.create_checkpoint("Second")
        self.store.restore_checkpoint(first["seq"])
        restored = self.store.get_file(file["file_id"])
        self.store.update_file(file["file_id"], "Notes", "one\ntwo alternate\nthree\n", restored["revision"])
        branch = self.store.create_checkpoint("Branch")

        tree = self.store.checkpoint_tree()
        by_seq = {item["seq"]: item for item in tree["items"]}
        branch_event = next(doc for doc in self.collection.documents if doc.get("seq") == branch["seq"])
        stored_files = branch_event["data"]["files"]

        self.assertEqual(tree["head_seq"], branch["seq"])
        self.assertEqual(by_seq[second["seq"]]["data"]["parent_seq"], first["seq"])
        self.assertEqual(by_seq[branch["seq"]]["data"]["parent_seq"], first["seq"])
        self.assertNotIn("files", by_seq[branch["seq"]]["data"])
        self.assertEqual(stored_files[0]["content"], "one\ntwo alternate\nthree\n")
        diff = self.store.checkpoint_diff(branch["seq"])["changes"][0]
        self.assertEqual(diff["before_content"], "one\ntwo\nthree\n")
        self.assertEqual(diff["after_content"], "one\ntwo alternate\nthree\n")
        self.assertEqual(diff["before_changed_lines"], [1])
        self.assertEqual(diff["after_changed_lines"], [1])
        self.assertIn("-two\n+two alternate\n", diff["diff"])
        self.assertEqual(self.store._checkpoint_state(branch["seq"])[0]["content"], "one\ntwo alternate\nthree\n")
        self.store.restore_checkpoint(branch["seq"])
        self.assertEqual(self.store.get_file(file["file_id"])["content"], "one\ntwo alternate\nthree\n")

    def test_current_workspace_collection_holds_edits_and_checkpoints_hold_full_snapshots(self):
        workspace = FakeWorkspaceCollection()
        store = FileStore(self.collection, workspace)
        created = store.create_file("Notes", "base\nkeep\n")
        store.update_file(created["file_id"], "Notes", "changed\nkeep\n", created["revision"])
        checkpoint = store.create_checkpoint("Base")
        changed = store.update_file(created["file_id"], "Notes", "edited\nkeep\n", store.get_file(created["file_id"])["revision"])

        persisted_events = [doc for doc in self.collection.documents if "type" in doc]
        self.assertEqual([event["type"] for event in persisted_events], ["workspace.checkpoint"])
        self.assertEqual(persisted_events[0]["data"]["files"][0]["content"], "changed\nkeep\n")
        self.assertNotIn("changes", persisted_events[0]["data"])
        self.assertEqual(store.get_file(created["file_id"])["content"], "edited\nkeep\n")

        replayed = FileStore(self.collection, workspace)
        self.assertEqual(replayed.get_file(created["file_id"])["content"], "edited\nkeep\n")
        self.assertEqual(replayed.checkpoint_tree()["head_seq"], checkpoint["seq"])
        replayed.restore_checkpoint(checkpoint["seq"])
        self.assertEqual(replayed.get_file(created["file_id"])["content"], "changed\nkeep\n")
        self.assertGreater(replayed.get_file(created["file_id"])["revision"], changed["revision"])
        self.assertEqual([doc["type"] for doc in self.collection.documents if "type" in doc], [
            "workspace.checkpoint", "workspace.restore",
        ])

        replayed.create_checkpoint("Restored branch")
        self.assertEqual(replayed.checkpoint_tree()["items"][-1]["data"]["parent_seq"], checkpoint["seq"])

    def test_workspace_reads_reflect_database_changes_without_restarting_store(self):
        workspace = FakeWorkspaceCollection()
        store = FileStore(self.collection, workspace)
        created = store.create_file("Mongo only", "content")

        self.assertFalse(hasattr(store, "_files"))
        self.assertEqual(len(store.list_files()), 1)
        workspace.delete_one({"_id": store._workspace_id(created["file_id"])})

        self.assertEqual(store.list_files(), [])
        with self.assertRaises(FileMissingError):
            store.get_file(created["file_id"])

    def test_legacy_file_events_are_not_replayed_or_migrated(self):
        self.collection.documents[0]["next_seq"] = 1
        self.collection.documents.append({
            "version": 1, "seq": 1, "event_id": "legacy", "type": "file.create",
            "file_id": "legacy-file", "timestamp": "2026-01-01T00:00:00+00:00",
            "data": {"name": "Legacy", "content": "old content", "pinned": False},
        })

        reopened = FileStore(self.collection, self.workspace)

        self.assertEqual(reopened.list_files(), [])
        self.assertFalse(any(doc.get("file_id") == "legacy-file" for doc in self.workspace.documents))
        checkpoint = reopened.create_checkpoint("New history")
        self.assertEqual(checkpoint["data"]["parent_seq"], None)

    def test_missing_checkpoint_cannot_be_restored(self):
        with self.assertRaises(FileMissingError):
            self.store.restore_checkpoint(999)


if __name__ == "__main__":
    unittest.main()
