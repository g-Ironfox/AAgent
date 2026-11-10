import threading
import uuid
from datetime import datetime, timezone
from typing import Any

from pymongo import ASCENDING, ReturnDocument
from pymongo.collection import Collection
from pymongo.errors import PyMongoError


class FileConflictError(Exception):
    pass


class FileMissingError(Exception):
    pass


class FileStoreUnavailableError(Exception):
    pass


class FileStore:
    """MongoDB-backed append-only event history with deterministic replay."""

    COUNTER_ID = "_workspace_file_event_counter"
    GENESIS_CHECKPOINT = {
        "version": 1,
        "seq": 0,
        "event_id": "workspace-genesis",
        "type": "workspace.checkpoint",
        "file_id": "workspace",
        "timestamp": "1970-01-01T00:00:00+00:00",
        "data": {"name": "初始状态", "files": []},
    }

    def __init__(self, events: Collection):
        self.events = events
        self._lock = threading.RLock()
        self._files: dict[str, dict[str, Any]] = {}
        self._revision = 0
        self._loaded = False
        self._load_error: PyMongoError | None = None
        self._load()

    @property
    def revision(self) -> int:
        with self._lock:
            self._ensure_loaded()
            return self._revision

    def list_files(self) -> list[dict[str, Any]]:
        with self._lock:
            self._ensure_loaded()
            items = [self._copy(file, False) for file in self._files.values()]
            return sorted(items, key=lambda item: (item["updated_at"], item["file_id"]), reverse=True)

    def get_file(self, file_id: str) -> dict[str, Any]:
        with self._lock:
            self._ensure_loaded()
            file = self._files.get(file_id)
            if file is None:
                raise FileMissingError
            return self._copy(file)

    def list_events(self, before_seq: int | None = None, limit: int = 50, file_id: str | None = None) -> list[dict[str, Any]]:
        with self._lock:
            self._ensure_loaded()
            query: dict[str, Any] = {"type": {"$exists": True}}
            if before_seq is not None:
                query["seq"] = {"$lt": before_seq}
            if file_id:
                query["file_id"] = file_id
            try:
                events = self.events.find(query).sort("seq", -1).limit(limit)
                return [{key: value for key, value in event.items() if key != "_id"} for event in events]
            except PyMongoError as error:
                self._loaded = False
                self._load_error = error
                raise FileStoreUnavailableError("workspace file event store is unavailable") from error

    def list_checkpoints(self, before_seq: int | None = None, limit: int = 50, file_id: str | None = None) -> list[dict[str, Any]]:
        with self._lock:
            self._ensure_loaded()
            query: dict[str, Any] = {"type": "workspace.checkpoint"}
            if before_seq is not None:
                query["seq"] = {"$lt": before_seq}
            if file_id:
                query["data.files.file_id"] = file_id
            try:
                checkpoints = self.events.find(query).sort("seq", -1).limit(limit)
                items = [{key: value for key, value in item.items() if key != "_id"} for item in checkpoints]
                if not file_id and (before_seq is None or before_seq > 0) and len(items) < limit:
                    items.append(self._copy(self.GENESIS_CHECKPOINT))
                return items
            except PyMongoError as error:
                self._loaded = False
                self._load_error = error
                raise FileStoreUnavailableError("workspace file event store is unavailable") from error

    def create_file(self, name: str, content: str = "") -> dict[str, Any]:
        file_id = uuid.uuid4().hex
        with self._lock:
            self._ensure_loaded()
            self._append("file.create", file_id, {"name": name, "content": content, "pinned": False})
            return self.get_file(file_id)

    def update_file(self, file_id: str, name: str, content: str, expected_revision: int) -> dict[str, Any]:
        with self._lock:
            self._ensure_loaded()
            current = self._require_file(file_id)
            self._check_revision(current, expected_revision)
            self._append("file.update", file_id, {"name": name, "content": content})
            return self.get_file(file_id)

    def set_pinned(self, file_id: str, pinned: bool, expected_revision: int) -> dict[str, Any]:
        with self._lock:
            self._ensure_loaded()
            current = self._require_file(file_id)
            self._check_revision(current, expected_revision)
            self._append("file.pin", file_id, {"pinned": pinned})
            return self.get_file(file_id)

    def delete_file(self, file_id: str, expected_revision: int) -> None:
        with self._lock:
            self._ensure_loaded()
            current = self._require_file(file_id)
            self._check_revision(current, expected_revision)
            self._append("file.delete", file_id, {})

    def create_checkpoint(self, name: str) -> dict[str, Any]:
        with self._lock:
            self._ensure_loaded()
            files = [self._copy(file) for file in self._files.values()]
            files.sort(key=lambda item: (item["name"].casefold(), item["file_id"]))
            return self._append("workspace.checkpoint", "workspace", {"name": name, "files": files})

    def restore_checkpoint(self, seq: int) -> dict[str, Any]:
        with self._lock:
            self._ensure_loaded()
            if seq == 0:
                checkpoint_data = self.GENESIS_CHECKPOINT["data"]
            elif seq > 0:
                try:
                    checkpoint = next(iter(self.events.find({"type": "workspace.checkpoint", "seq": seq})), None)
                except PyMongoError as error:
                    self._loaded = False
                    self._load_error = error
                    raise FileStoreUnavailableError("workspace file event store is unavailable") from error
                if checkpoint is None:
                    raise FileMissingError
                checkpoint_data = checkpoint["data"]
            else:
                raise FileMissingError
            files = [self._copy(file) for file in checkpoint_data["files"]]
            return self._append("workspace.restore", "workspace", {
                "checkpoint_seq": seq,
                "name": checkpoint_data["name"],
                "files": files,
            })

    def _load(self) -> None:
        try:
            self.events.create_index([("seq", ASCENDING)], unique=True, name="workspace_file_event_seq")
            stored_events = list(self.events.find({"type": {"$exists": True}}).sort("seq", ASCENDING))
            revision = stored_events[-1]["seq"] if stored_events else 0
            self.events.find_one_and_update(
                {"_id": self.COUNTER_ID},
                {"$setOnInsert": {"next_seq": revision}},
                upsert=True,
                return_document=ReturnDocument.AFTER,
            )
            for event in stored_events:
                self._apply(event)
            self._loaded = True
            self._load_error = None
        except PyMongoError as error:
            self._load_error = error
            self._loaded = False
            self._files.clear()
            self._revision = 0

    def _ensure_loaded(self) -> None:
        if not self._loaded:
            self._load()
        if not self._loaded:
            raise FileStoreUnavailableError("workspace file event store is unavailable") from self._load_error

    def _append(self, event_type: str, file_id: str, data: dict[str, Any]) -> dict[str, Any]:
        try:
            counter = self.events.find_one_and_update(
                {"_id": self.COUNTER_ID},
                {"$inc": {"next_seq": 1}},
                return_document=ReturnDocument.AFTER,
            )
            if counter is None:
                raise RuntimeError("workspace event counter was not initialized")
            event = {
                "version": 1,
                "seq": counter["next_seq"],
                "event_id": uuid.uuid4().hex,
                "type": event_type,
                "file_id": file_id,
                "timestamp": self._now(),
                "data": data,
            }
            self.events.insert_one(event)
        except PyMongoError as error:
            self._loaded = False
            self._load_error = error
            raise FileStoreUnavailableError("workspace file event store is unavailable") from error
        self._apply(event)
        return {key: value for key, value in event.items() if key != "_id"}

    def _apply(self, event: dict[str, Any]) -> None:
        if event.get("version") != 1:
            raise RuntimeError("unsupported workspace file event version")
        if event["seq"] <= self._revision:
            raise RuntimeError("workspace file event sequence is not strictly increasing")
        file_id = event["file_id"]
        data = event["data"]
        event_type = event["type"]
        if event_type == "file.create":
            if file_id in self._files:
                raise RuntimeError("duplicate workspace file id")
            self._files[file_id] = {
                "file_id": file_id,
                **data,
                "created_at": event["timestamp"],
                "updated_at": event["timestamp"],
                "revision": event["seq"],
            }
        elif event_type == "file.update":
            file = self._replay_target(file_id)
            file.update(data)
            file["updated_at"] = event["timestamp"]
            file["revision"] = event["seq"]
        elif event_type == "file.pin":
            file = self._replay_target(file_id)
            file["pinned"] = data["pinned"]
            file["revision"] = event["seq"]
        elif event_type == "file.delete":
            self._replay_target(file_id)
            del self._files[file_id]
        elif event_type == "workspace.checkpoint":
            pass
        elif event_type == "workspace.restore":
            restored = {}
            for snapshot in data["files"]:
                file = self._copy(snapshot)
                file["updated_at"] = event["timestamp"]
                file["revision"] = event["seq"]
                restored[file["file_id"]] = file
            if len(restored) != len(data["files"]):
                raise RuntimeError("duplicate workspace file id in restore snapshot")
            self._files = restored
        else:
            raise RuntimeError("unknown workspace file event type")
        self._revision = event["seq"]

    def _replay_target(self, file_id: str) -> dict[str, Any]:
        file = self._files.get(file_id)
        if file is None:
            raise RuntimeError("workspace event references missing file")
        return file

    def _require_file(self, file_id: str) -> dict[str, Any]:
        file = self._files.get(file_id)
        if file is None:
            raise FileMissingError
        return file

    @staticmethod
    def _check_revision(file: dict[str, Any], expected_revision: int) -> None:
        if file["revision"] != expected_revision:
            raise FileConflictError

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _copy(file: dict[str, Any], include_content: bool = True) -> dict[str, Any]:
        result = dict(file)
        if not include_content:
            result.pop("content", None)
        return result
