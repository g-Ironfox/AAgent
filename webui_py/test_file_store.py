import unittest

from pymongo.errors import ServerSelectionTimeoutError

from file_store import FileConflictError, FileMissingError, FileStore, FileStoreUnavailableError


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

    def find(self, query):
        self._check()
        events = [doc for doc in self.documents if "type" in doc]
        if "type" in query and isinstance(query["type"], str):
            events = [doc for doc in events if doc["type"] == query["type"]]
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

    def find_one(self, query):
        return next((dict(doc) for doc in self.documents if doc.get("_id") == query["_id"]), None)

    def find(self, query):
        return FakeCursor([dict(doc) for doc in self.documents if doc.get("generation") == query["generation"]])

    def insert_one(self, document):
        if any(doc.get("_id") == document["_id"] for doc in self.documents):
            raise RuntimeError("duplicate key")
        self.documents.append(dict(document))

    def replace_one(self, query, document, upsert=False):
        for index, current in enumerate(self.documents):
            if current.get("_id") == query["_id"]:
                self.documents[index] = dict(document)
                return
        if upsert:
            self.documents.append(dict(document))

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
        self.store = FileStore(self.collection)

    def test_mutations_replay_to_same_state(self):
        created = self.store.create_file("First", "initial")
        updated = self.store.update_file(created["file_id"], "Renamed", "body", created["revision"])
        pinned = self.store.set_pinned(updated["file_id"], True, updated["revision"])

        replayed = FileStore(self.collection)

        self.assertEqual(replayed.get_file(created["file_id"]), pinned)
        self.assertEqual(replayed.revision, 3)
        self.assertEqual([item["type"] for item in self.collection.documents if "type" in item], [
            "file.create", "file.update", "file.pin"
        ])

        replayed.delete_file(created["file_id"], pinned["revision"])
        self.assertEqual(replayed.list_files(), [])
        self.assertEqual(FileStore(self.collection).list_files(), [])

    def test_stale_revision_is_rejected_without_appending(self):
        created = self.store.create_file("First")
        updated = self.store.update_file(created["file_id"], "Second", "", created["revision"])

        with self.assertRaises(FileConflictError):
            self.store.update_file(created["file_id"], "Stale", "", created["revision"])

        self.assertEqual(self.store.revision, updated["revision"])
        self.assertEqual(len([doc for doc in self.collection.documents if "type" in doc]), 2)

    def test_missing_file_is_rejected(self):
        with self.assertRaises(FileMissingError):
            self.store.get_file("missing")

    def test_mongo_unavailable_is_reported_without_blocking_construction(self):
        store = FileStore(FakeCollection(fail=True))

        with self.assertRaises(FileStoreUnavailableError):
            store.list_files()

    def test_counter_document_is_not_replayed_as_an_event(self):
        self.store.create_file("First")

        self.assertEqual(len(self.collection.documents), 2)
        self.assertNotIn("seq", self.collection.documents[0])
        self.assertIn("next_seq", self.collection.documents[0])

    def test_events_can_be_filtered_and_paginated_by_sequence(self):
        first = self.store.create_file("First")
        second = self.store.create_file("Second")
        self.store.update_file(first["file_id"], "First renamed", "changed", first["revision"])

        self.assertEqual([event["seq"] for event in self.store.list_events(limit=2)], [3, 2])
        self.assertEqual(
            [event["seq"] for event in self.store.list_events(before_seq=3, file_id=first["file_id"])],
            [1],
        )
        self.assertEqual(self.store.list_events(before_seq=2, file_id=second["file_id"]), [])

    def test_checkpoint_keeps_an_immutable_workspace_diff(self):
        created = self.store.create_file("First", "before checkpoint")

        checkpoint = self.store.create_checkpoint("Before refactor")
        self.store.update_file(created["file_id"], "First", "after checkpoint", created["revision"])
        replayed = FileStore(self.collection)

        self.assertEqual(checkpoint["type"], "workspace.checkpoint")
        self.assertIsNone(checkpoint["data"]["parent_seq"])
        self.assertEqual(checkpoint["data"]["changes"][0]["content_patches"][0]["lines"], ["before checkpoint"])
        self.assertEqual(replayed.get_file(created["file_id"])["content"], "after checkpoint")
        self.assertEqual(replayed._checkpoint_state(checkpoint["seq"])[0]["content"], "before checkpoint")
        self.assertEqual(replayed.list_checkpoints()[0]["seq"], checkpoint["seq"])
        self.assertEqual(replayed.list_checkpoints(file_id=created["file_id"])[0]["seq"], checkpoint["seq"])
        self.assertEqual(replayed.revision, 3)

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

    def test_genesis_checkpoint_is_restorable_and_replays_as_empty_workspace(self):
        self.store.create_file("Seeded file", "from replayed history")

        restored = self.store.restore_checkpoint(0)
        replayed = FileStore(self.collection)

        self.assertEqual(restored["data"]["checkpoint_seq"], 0)
        self.assertEqual(self.store.list_files(), [])
        self.assertEqual(replayed.list_files(), [])
        self.assertEqual(replayed.revision, restored["seq"])

    def test_restore_checkpoint_replaces_workspace_and_replays(self):
        original = self.store.create_file("Original", "before")
        checkpoint = self.store.create_checkpoint("Known good")
        self.store.update_file(original["file_id"], "Changed", "after", original["revision"])
        self.store.create_file("Extra", "remove me")

        restored = self.store.restore_checkpoint(checkpoint["seq"])
        files = self.store.list_files()
        replayed = FileStore(self.collection)

        self.assertEqual(restored["type"], "workspace.restore")
        self.assertEqual(restored["data"]["checkpoint_seq"], checkpoint["seq"])
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0]["file_id"], original["file_id"])
        self.assertEqual(files[0]["name"], "Original")
        self.assertEqual(self.store.get_file(original["file_id"])["content"], "before")
        self.assertEqual(files[0]["revision"], restored["seq"])
        self.assertEqual(replayed.list_files(), files)

    def test_restore_checkpoint_can_restore_empty_workspace(self):
        checkpoint = self.store.create_checkpoint("Empty")
        self.store.create_file("Later")

        self.store.restore_checkpoint(checkpoint["seq"])

        self.assertEqual(self.store.list_files(), [])

    def test_checkpoint_tree_branches_after_restore_and_stores_only_changed_lines(self):
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
        stored_change = branch_event["data"]["changes"][0]

        self.assertEqual(tree["head_seq"], branch["seq"])
        self.assertEqual(by_seq[second["seq"]]["data"]["parent_seq"], first["seq"])
        self.assertEqual(by_seq[branch["seq"]]["data"]["parent_seq"], first["seq"])
        self.assertEqual(stored_change["content_patches"], [{
            "start": 1, "end": 2, "old_lines": ["two\n"], "lines": ["two alternate\n"],
        }])
        self.assertIn("-two\n+two alternate\n", self.store.checkpoint_diff(branch["seq"])["changes"][0]["diff"])
        self.assertEqual(self.store._checkpoint_state(branch["seq"])[0]["content"], "one\ntwo alternate\nthree\n")
        self.store.restore_checkpoint(branch["seq"])
        self.assertEqual(self.store.get_file(file["file_id"])["content"], "one\ntwo alternate\nthree\n")

    def test_current_workspace_collection_holds_edits_and_checkpoints_hold_only_diffs(self):
        workspace = FakeWorkspaceCollection()
        store = FileStore(self.collection, workspace)
        created = store.create_file("Notes", "base\nkeep\n")
        store.update_file(created["file_id"], "Notes", "changed\nkeep\n", created["revision"])
        checkpoint = store.create_checkpoint("Base")
        changed = store.update_file(created["file_id"], "Notes", "edited\nkeep\n", store.get_file(created["file_id"])["revision"])

        persisted_events = [doc for doc in self.collection.documents if "type" in doc]
        self.assertEqual([event["type"] for event in persisted_events], ["workspace.checkpoint"])
        self.assertEqual(persisted_events[0]["data"]["changes"][0]["content_patches"][0]["old_lines"], [])
        self.assertEqual(store.get_file(created["file_id"])["content"], "edited\nkeep\n")

        replayed = FileStore(self.collection, workspace)
        self.assertEqual(replayed.get_file(created["file_id"])["content"], "edited\nkeep\n")
        self.assertEqual(replayed.checkpoint_tree()["head_seq"], checkpoint["seq"])
        replayed.restore_checkpoint(checkpoint["seq"])
        self.assertEqual(replayed.get_file(created["file_id"])["content"], "changed\nkeep\n")
        self.assertGreater(replayed.get_file(created["file_id"])["revision"], changed["revision"])
        self.assertEqual(len([doc for doc in self.collection.documents if "type" in doc]), 1)

        replayed.create_checkpoint("Restored branch")
        self.assertEqual(replayed.checkpoint_tree()["items"][-1]["data"]["parent_seq"], checkpoint["seq"])

    def test_legacy_event_state_is_migrated_to_workspace_collection_once(self):
        created = self.store.create_file("Legacy", "from event history")
        checkpoint = self.store.create_checkpoint("Legacy checkpoint")
        workspace = FakeWorkspaceCollection()

        migrated = FileStore(self.collection, workspace)
        migrated.update_file(created["file_id"], "Legacy updated", "current collection", created["revision"])
        reopened = FileStore(self.collection, workspace)

        self.assertEqual(reopened.get_file(created["file_id"])["content"], "current collection")
        self.assertEqual(reopened.checkpoint_tree()["head_seq"], checkpoint["seq"])
        self.assertEqual([doc["type"] for doc in self.collection.documents if "type" in doc], [
            "file.create", "workspace.checkpoint",
        ])

    def test_missing_checkpoint_cannot_be_restored(self):
        with self.assertRaises(FileMissingError):
            self.store.restore_checkpoint(999)


if __name__ == "__main__":
    unittest.main()
