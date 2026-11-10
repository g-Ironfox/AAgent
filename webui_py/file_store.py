import difflib
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
    """Keep the live workspace separately and persist checkpoint-only history."""

    COUNTER_ID = "_workspace_file_event_counter"
    WORKSPACE_META_ID = "_workspace_current_state"
    def __init__(self, events: Collection, workspace: Collection | None = None):
        self.events = events
        self.workspace = workspace
        self._lock = threading.RLock()
        self._files: dict[str, dict[str, Any]] = {}
        self._revision = 0
        self._head_checkpoint_seq = 0
        self._workspace_generation = 0
        self._file_revision = 0
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
            try:
                self._ensure_loaded()
                query: dict[str, Any] = {"type": "workspace.checkpoint"}
                if before_seq is not None:
                    query["seq"] = {"$lt": before_seq}
                items = [self._clean_event(item) for item in self.events.find(query).sort("seq", -1)]
                if file_id:
                    items = [item for item in items if any(
                        file["file_id"] == file_id for file in self._checkpoint_state(item["seq"])
                    )]
                items = items[:limit]
                return items
            except PyMongoError as error:
                self._loaded = False
                self._load_error = error
                raise FileStoreUnavailableError("workspace file event store is unavailable") from error

    def create_file(self, name: str, content: str = "") -> dict[str, Any]:
        file_id = uuid.uuid4().hex
        with self._lock:
            self._ensure_loaded()
            if self.workspace is not None:
                timestamp = self._now()
                file = {
                    "file_id": file_id, "name": name, "content": content, "pinned": False,
                    "created_at": timestamp, "updated_at": timestamp,
                    "revision": self._next_file_revision(),
                }
                self._workspace_write(lambda: self.workspace.insert_one(self._workspace_document(file)))
                self._files[file_id] = file
                return self._copy(file)
            self._append("file.create", file_id, {"name": name, "content": content, "pinned": False})
            return self.get_file(file_id)

    def update_file(self, file_id: str, name: str, content: str, expected_revision: int) -> dict[str, Any]:
        with self._lock:
            self._ensure_loaded()
            current = self._require_file(file_id)
            self._check_revision(current, expected_revision)
            if self.workspace is not None:
                updated = self._copy(current)
                updated.update({"name": name, "content": content, "updated_at": self._now()})
                updated["revision"] = self._next_file_revision()
                self._workspace_write(lambda: self.workspace.replace_one(
                    {"_id": self._workspace_id(file_id)}, self._workspace_document(updated), upsert=True
                ))
                self._files[file_id] = updated
                return self._copy(updated)
            self._append("file.update", file_id, {"name": name, "content": content})
            return self.get_file(file_id)

    def set_pinned(self, file_id: str, pinned: bool, expected_revision: int) -> dict[str, Any]:
        with self._lock:
            self._ensure_loaded()
            current = self._require_file(file_id)
            self._check_revision(current, expected_revision)
            if self.workspace is not None:
                updated = self._copy(current)
                updated["pinned"] = pinned
                updated["revision"] = self._next_file_revision()
                self._workspace_write(lambda: self.workspace.replace_one(
                    {"_id": self._workspace_id(file_id)}, self._workspace_document(updated), upsert=True
                ))
                self._files[file_id] = updated
                return self._copy(updated)
            self._append("file.pin", file_id, {"pinned": pinned})
            return self.get_file(file_id)

    def delete_file(self, file_id: str, expected_revision: int) -> None:
        with self._lock:
            self._ensure_loaded()
            current = self._require_file(file_id)
            self._check_revision(current, expected_revision)
            if self.workspace is not None:
                self._workspace_write(lambda: self.workspace.delete_one({"_id": self._workspace_id(file_id)}))
                del self._files[file_id]
                return
            self._append("file.delete", file_id, {})

    def create_checkpoint(self, name: str) -> dict[str, Any]:
        with self._lock:
            self._ensure_loaded()
            parent_seq = self._head_checkpoint_seq or None
            parent_files = {item["file_id"]: item for item in self._checkpoint_state(parent_seq or 0)}
            changes = self._diff_files(parent_files, self._files)
            return self._append("workspace.checkpoint", "workspace", {
                "name": name, "parent_seq": parent_seq, "changes": changes,
            })

    def checkpoint_tree(self) -> dict[str, Any]:
        with self._lock:
            self._ensure_loaded()
            try:
                events = [self._clean_event(item) for item in self.events.find(
                    {"type": {"$exists": True}}
                ).sort("seq", ASCENDING) if item.get("type") in ("workspace.checkpoint", "workspace.restore")]
            except PyMongoError as error:
                self._loaded = False
                self._load_error = error
                raise FileStoreUnavailableError("workspace file event store is unavailable") from error
            items = []
            head_seq = 0
            for event in events:
                if event["type"] == "workspace.restore":
                    head_seq = event["data"]["checkpoint_seq"]
                    continue
                event["data"].setdefault("parent_seq", head_seq)
                head_seq = event["seq"]
                if event["data"].get("parent_seq") == 0:
                    event["data"]["parent_seq"] = None
                items.append(event)
            return {"items": items, "head_seq": self._head_checkpoint_seq or None}

    def checkpoint_diff(self, seq: int) -> dict[str, Any]:
        with self._lock:
            self._ensure_loaded()
            if seq == 0:
                return {"seq": 0, "parent_seq": None, "changes": []}
            checkpoint = self._get_checkpoint(seq)
            if checkpoint is None:
                raise FileMissingError
            data = checkpoint["data"]
            if "changes" not in data:
                parent_seq = data.get("parent_seq", 0)
                before = {item["file_id"]: item for item in self._checkpoint_state(parent_seq)}
                after = {item["file_id"]: item for item in data.get("files", [])}
                changes = self._diff_files(before, after)
            else:
                changes = data["changes"]
            return {
                "seq": seq,
                "parent_seq": data.get("parent_seq") or None,
                "changes": [self._display_change(change) for change in changes],
            }

    def restore_checkpoint(self, seq: int) -> dict[str, Any]:
        with self._lock:
            self._ensure_loaded()
            if seq < 0:
                raise FileMissingError
            checkpoint = self._get_checkpoint(seq)
            if seq and checkpoint is None:
                raise FileMissingError
            checkpoint_data = {"name": "Empty workspace"} if seq == 0 else checkpoint["data"]
            files = [self._copy(file) for file in self._checkpoint_state(seq)]
            if self.workspace is not None:
                generation = self._workspace_generation + 1
                restored = {}
                for file in files:
                    file["revision"] = self._next_file_revision()
                    file["updated_at"] = self._now()
                    restored[file["file_id"]] = file
                self._workspace_write(lambda: self.workspace.delete_many({"generation": generation}))
                self._workspace_write(lambda: [
                    self.workspace.insert_one(self._workspace_document(file, generation))
                    for file in restored.values()
                ])
                self._workspace_generation = generation
                self._files = restored
                self._head_checkpoint_seq = seq
                self._persist_workspace_meta()
                self._workspace_write(lambda: self.workspace.delete_many({"generation": {"$ne": generation}}))
                return {
                    "version": 1, "seq": self._revision, "event_id": uuid.uuid4().hex,
                    "type": "workspace.restore", "file_id": "workspace", "timestamp": self._now(),
                    "data": {"checkpoint_seq": seq, "name": checkpoint_data["name"]},
                }
            return self._append("workspace.restore", "workspace", {
                "checkpoint_seq": seq,
                "name": checkpoint_data["name"],
                "files": files,
            })

    def _checkpoint_state(self, seq: int) -> list[dict[str, Any]]:
        if seq == 0:
            return []
        chain = []
        current_seq = seq
        files = {}
        while current_seq:
            checkpoint = self._get_checkpoint(current_seq)
            if checkpoint is None:
                raise FileMissingError
            data = checkpoint["data"]
            if "files" in data:
                files = {item["file_id"]: self._copy(item) for item in data["files"]}
                break
            chain.append(data)
            current_seq = data.get("parent_seq", 0)
        for data in reversed(chain):
            for change in data.get("changes", []):
                file_id = change["file_id"]
                if change.get("after") is None:
                    files.pop(file_id, None)
                    continue
                previous = files.get(file_id, {})
                lines = previous.get("content", "").splitlines(keepends=True)
                for patch in reversed(change.get("content_patches", [])):
                    lines[patch["start"]:patch["end"]] = patch["lines"]
                files[file_id] = {
                    **previous, **change["after"], "file_id": file_id, "content": "".join(lines),
                }
        return sorted(files.values(), key=lambda item: (item["name"].casefold(), item["file_id"]))

    def _get_checkpoint(self, seq: int) -> dict[str, Any] | None:
        try:
            return next(iter(self.events.find({"type": "workspace.checkpoint", "seq": seq})), None)
        except PyMongoError as error:
            self._loaded = False
            self._load_error = error
            raise FileStoreUnavailableError("workspace file event store is unavailable") from error

    @staticmethod
    def _diff_files(before: dict[str, dict[str, Any]], after: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
        changes = []
        for file_id in sorted(before.keys() | after.keys()):
            old, new = before.get(file_id), after.get(file_id)
            old_content = (old or {}).get("content", "")
            new_content = (new or {}).get("content", "")
            old_meta = None if old is None else {key: old.get(key) for key in ("name", "pinned", "created_at")}
            new_meta = None if new is None else {key: new.get(key) for key in ("name", "pinned", "created_at")}
            old_lines = old_content.splitlines(keepends=True)
            new_lines = new_content.splitlines(keepends=True)
            patches = [
                {"start": i1, "end": i2, "old_lines": old_lines[i1:i2], "lines": new_lines[j1:j2]}
                for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(
                    a=old_lines, b=new_lines, autojunk=False
                ).get_opcodes()
                if tag != "equal"
            ]
            if old_meta != new_meta or old_content != new_content:
                changes.append({
                    "file_id": file_id, "before": old_meta, "after": new_meta,
                    "content_patches": patches,
                })
        return changes

    @staticmethod
    def _display_change(change: dict[str, Any]) -> dict[str, Any]:
        before, after = change.get("before"), change.get("after")
        status = "added" if before is None else "deleted" if after is None else "modified"
        lines = []
        for patch in change.get("content_patches", []):
            lines.append(f"@@ -{patch['start'] + 1},{patch['end'] - patch['start']} +{patch['start'] + 1},{len(patch['lines'])} @@\n")
            if before is not None:
                lines.extend("-" + line for line in patch.get("old_lines", []))
            lines.extend("+" + line for line in patch["lines"])
        return {
            "file_id": change["file_id"], "status": status,
            "before_name": before and before.get("name"),
            "after_name": after and after.get("name"),
            "diff": "".join(lines),
        }

    @staticmethod
    def _clean_event(event: dict[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in event.items() if key != "_id"}

    def _load(self) -> None:
        try:
            self._files.clear()
            self._revision = 0
            self._head_checkpoint_seq = 0
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
            if self.workspace is not None:
                self._load_workspace_state()
            self._loaded = True
            self._load_error = None
        except PyMongoError as error:
            self._load_error = error
            self._loaded = False
            self._files.clear()
            self._revision = 0

    def _load_workspace_state(self) -> None:
        meta = self.workspace.find_one({"_id": self.WORKSPACE_META_ID})
        if meta and meta.get("initialized"):
            self._workspace_generation = meta.get("generation", 1)
            self._file_revision = meta.get("file_revision", 0)
            self._head_checkpoint_seq = meta.get("head_checkpoint_seq", self._head_checkpoint_seq)
            if meta.get("head_event_seq", self._revision) < self._revision:
                latest_checkpoint = self.events.find_one({"type": "workspace.checkpoint"}, sort=[("seq", -1)])
                if latest_checkpoint:
                    self._head_checkpoint_seq = latest_checkpoint["seq"]
            self._files = {
                item["file_id"]: {key: value for key, value in item.items() if key not in ("_id", "generation")}
                for item in self.workspace.find({"generation": self._workspace_generation})
                if item.get("file_id")
            }
            self._workspace_write(lambda: self.workspace.delete_many({"generation": {"$ne": self._workspace_generation}}))
            return
        self._workspace_generation = 1
        self._file_revision = max((item.get("revision", 0) for item in self._files.values()), default=0)
        self._workspace_write(lambda: self.workspace.delete_many({"generation": 1}))
        self._workspace_write(lambda: [
            self.workspace.insert_one(self._workspace_document(file)) for file in self._files.values()
        ])
        self._persist_workspace_meta()

    def _workspace_id(self, file_id: str, generation: int | None = None) -> str:
        return f"{self._workspace_generation if generation is None else generation}:{file_id}"

    def _workspace_document(self, file: dict[str, Any], generation: int | None = None) -> dict[str, Any]:
        document = self._copy(file)
        document["_id"] = self._workspace_id(file["file_id"], generation)
        document["generation"] = self._workspace_generation if generation is None else generation
        return document

    def _persist_workspace_meta(self) -> None:
        meta = {
            "_id": self.WORKSPACE_META_ID, "initialized": True,
            "generation": self._workspace_generation, "file_revision": self._file_revision,
            "head_checkpoint_seq": self._head_checkpoint_seq, "head_event_seq": self._revision,
        }
        self._workspace_write(lambda: self.workspace.replace_one({"_id": self.WORKSPACE_META_ID}, meta, upsert=True))

    def _next_file_revision(self) -> int:
        self._file_revision += 1
        if self.workspace is not None:
            self._persist_workspace_meta()
        return self._file_revision

    def _workspace_write(self, operation) -> None:
        try:
            operation()
        except PyMongoError as error:
            self._loaded = False
            self._load_error = error
            raise FileStoreUnavailableError("workspace file store is unavailable") from error

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
        if self.workspace is not None and event_type == "workspace.checkpoint":
            self._persist_workspace_meta()
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
            data.setdefault("parent_seq", self._head_checkpoint_seq)
            self._head_checkpoint_seq = event["seq"]
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
            self._head_checkpoint_seq = data["checkpoint_seq"]
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
