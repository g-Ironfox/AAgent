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
            events = [doc for doc in events if doc["seq"] < query["seq"]["$lt"]]
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

    def test_checkpoint_keeps_an_immutable_workspace_snapshot(self):
        created = self.store.create_file("First", "before checkpoint")

        checkpoint = self.store.create_checkpoint("Before refactor")
        self.store.update_file(created["file_id"], "First", "after checkpoint", created["revision"])
        replayed = FileStore(self.collection)

        self.assertEqual(checkpoint["type"], "workspace.checkpoint")
        self.assertEqual(checkpoint["data"]["files"][0]["content"], "before checkpoint")
        self.assertEqual(replayed.get_file(created["file_id"])["content"], "after checkpoint")
        self.assertEqual(replayed.list_events(limit=10)[1]["data"]["files"][0]["content"], "before checkpoint")
        self.assertEqual(replayed.list_checkpoints()[0]["seq"], checkpoint["seq"])
        self.assertEqual(replayed.list_checkpoints(file_id=created["file_id"])[0]["seq"], checkpoint["seq"])
        self.assertEqual(replayed.revision, 3)


if __name__ == "__main__":
    unittest.main()
