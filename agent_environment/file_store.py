import difflib
import threading
import uuid
from datetime import datetime, timezone
from typing import Any

from pymongo import ASCENDING, ReturnDocument
from pymongo.collation import Collation
from pymongo.collection import Collection
from pymongo.errors import DuplicateKeyError, PyMongoError

from permissions import normalize_permissions


class FileConflictError(Exception):
    pass


class FileNameConflictError(FileConflictError):
    pass


class FileMissingError(Exception):
    pass


class FileStoreUnavailableError(Exception):
    pass


class FileStore:
    """Read live files from MongoDB and persist full checkpoint snapshots."""

    COUNTER_ID = "_workspace_file_event_counter"
    WORKSPACE_META_ID = "_workspace_current_state"

    def __init__(self, events: Collection, workspace: Collection):
        self.events = events
        self.workspace = workspace
        self._lock = threading.RLock()
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
            items = [self._copy(file, include_content=False) for file in self._current_files(include_content=False)]
            return sorted(items, key=lambda item: (item["updated_at"], item["file_id"]), reverse=True)

    def get_file(self, file_id: str) -> dict[str, Any]:
        with self._lock:
            self._ensure_loaded()
            file = self._require_file(file_id)
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
                items = [self._clean_event(item) for item in self.events.find(
                    query,
                    {
                        "seq": 1, "version": 1, "event_id": 1, "type": 1,
                        "file_id": 1, "timestamp": 1, "data.name": 1, "data.parent_seq": 1,
                    },
                ).sort("seq", -1)]
                if file_id:
                    items = [item for item in items if any(
                        file["file_id"] == file_id for file in self._checkpoint_state(item["seq"])
                    )]
                for item in items:
                    item["data"] = {
                        key: value for key, value in item["data"].items()
                        if key not in ("files", "changes")
                    }
                items = items[:limit]
                return items
            except PyMongoError as error:
                self._loaded = False
                self._load_error = error
                raise FileStoreUnavailableError("workspace file event store is unavailable") from error

    def create_file(
        self, name: str, content: str = "", permissions: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        file_id = uuid.uuid4().hex
        with self._lock:
            self._ensure_loaded()
            self._check_unique_file_name(name)
            timestamp = self._now()
            file = {
                "file_id": file_id, "name": name, "content": content, "pinned": False,
                "permissions": normalize_permissions(permissions),
                "created_at": timestamp, "updated_at": timestamp,
                "revision": self._next_file_revision(),
            }
            self._workspace_write(
                lambda: self.workspace.insert_one(self._workspace_document(file)),
                duplicate_is_conflict=True,
            )
            return self._copy(file)

    def update_file(
        self, file_id: str, name: str, content: str, expected_revision: int,
        permissions: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            self._ensure_loaded()
            current = self._require_file(file_id)
            self._check_revision(current, expected_revision)
            self._check_unique_file_name(name, exclude_file_id=file_id)
            updated = self._copy(current)
            updated.update({"name": name, "content": content, "updated_at": self._now()})
            updated["permissions"] = normalize_permissions(
                permissions if permissions is not None else updated.get("permissions")
            )
            updated["revision"] = self._next_file_revision()
            self._workspace_write(
                lambda: self.workspace.replace_one(
                    {"_id": self._workspace_id(file_id)}, self._workspace_document(updated), upsert=False
                ),
                duplicate_is_conflict=True,
            )
            return self._copy(updated)

    def set_pinned(self, file_id: str, pinned: bool, expected_revision: int) -> dict[str, Any]:
        with self._lock:
            self._ensure_loaded()
            current = self._require_file(file_id)
            self._check_revision(current, expected_revision)
            updated = self._copy(current)
            updated["pinned"] = pinned
            updated["revision"] = self._next_file_revision()
            self._workspace_write(lambda: self.workspace.replace_one(
                {"_id": self._workspace_id(file_id)}, self._workspace_document(updated), upsert=False
            ))
            return self._copy(updated)

    def delete_file(self, file_id: str, expected_revision: int) -> None:
        with self._lock:
            self._ensure_loaded()
            current = self._require_file(file_id)
            self._check_revision(current, expected_revision)
            self._workspace_write(lambda: self.workspace.delete_one({"_id": self._workspace_id(file_id)}))

    def create_checkpoint(self, name: str) -> dict[str, Any]:
        with self._lock:
            self._ensure_loaded()
            parent_seq = self._head_checkpoint_seq or None
            return self._append("workspace.checkpoint", "workspace", {
                "name": name, "parent_seq": parent_seq,
                "files": [self._copy(file) for file in self._current_files()],
            })

    def checkpoint_tree(self) -> dict[str, Any]:
        with self._lock:
            self._ensure_loaded()
            try:
                events = [self._clean_event(item) for item in self.events.find(
                    {"type": {"$in": ["workspace.checkpoint", "workspace.restore"]}},
                    {
                        "seq": 1, "type": 1, "timestamp": 1,
                        "data.name": 1, "data.parent_seq": 1, "data.checkpoint_seq": 1,
                    },
                ).sort("seq", ASCENDING)]
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
                event["data"] = {
                    key: value for key, value in event["data"].items()
                    if key not in ("files", "changes")
                }
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
            parent_seq = data.get("parent_seq", 0)
            before = {item["file_id"]: item for item in self._checkpoint_state(parent_seq)}
            after = {item["file_id"]: item for item in self._checkpoint_state(seq)}
            changes = self._diff_files(before, after)
            return {
                "seq": seq,
                "parent_seq": parent_seq or None,
                "changes": [
                    self._display_change(change, before.get(change["file_id"]), after.get(change["file_id"]))
                    for change in changes
                ],
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
            names = [file["name"] for file in files]
            if len(names) != len(set(names)):
                raise FileNameConflictError("checkpoint contains duplicate file names")
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
            restore_event = self._append("workspace.restore", "workspace", {
                "checkpoint_seq": seq, "name": checkpoint_data["name"],
            })
            self._workspace_write(lambda: self.workspace.delete_many({"generation": {"$ne": generation}}))
            return restore_event

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
            metadata_fields = ("name", "pinned", "created_at", "permissions")
            old_meta = None if old is None else {key: old.get(key) for key in metadata_fields}
            new_meta = None if new is None else {key: new.get(key) for key in metadata_fields}
            old_lines = old_content.splitlines(keepends=True)
            new_lines = new_content.splitlines(keepends=True)
            patches = [
                {"start": i1, "end": i2, "new_start": j1,
                 "old_lines": old_lines[i1:i2], "lines": new_lines[j1:j2]}
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
    def _display_change(
        change: dict[str, Any],
        before_file: dict[str, Any] | None,
        after_file: dict[str, Any] | None,
    ) -> dict[str, Any]:
        before, after = change.get("before"), change.get("after")
        status = "added" if before is None else "deleted" if after is None else "modified"
        lines = []
        before_changed_lines = []
        after_changed_lines = []
        for patch in change.get("content_patches", []):
            lines.append(f"@@ -{patch['start'] + 1},{patch['end'] - patch['start']} +{patch['start'] + 1},{len(patch['lines'])} @@\n")
            if before is not None:
                lines.extend("-" + line for line in patch.get("old_lines", []))
            lines.extend("+" + line for line in patch["lines"])
            before_changed_lines.extend(range(patch["start"], patch["end"]))
            after_changed_lines.extend(range(patch["new_start"], patch["new_start"] + len(patch["lines"])))
        return {
            "file_id": change["file_id"], "status": status,
            "before_name": before and before.get("name"),
            "after_name": after and after.get("name"),
            "before_permissions": before and before.get("permissions"),
            "after_permissions": after and after.get("permissions"),
            "diff": "".join(lines),
            "before_content": before_file and before_file.get("content", ""),
            "after_content": after_file and after_file.get("content", ""),
            "before_changed_lines": before_changed_lines,
            "after_changed_lines": after_changed_lines,
        }

    @staticmethod
    def _clean_event(event: dict[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in event.items() if key != "_id"}

    def _load(self) -> None:
        try:
            self._revision = 0
            self._head_checkpoint_seq = 0
            self.events.create_index([("seq", ASCENDING)], unique=True, name="workspace_file_event_seq")
            self.workspace.create_index(
                [("generation", ASCENDING), ("name", ASCENDING)],
                unique=True,
                partialFilterExpression={"file_id": {"$exists": True}},
                collation=Collation(locale="simple"),
                name="workspace_generation_file_name",
            )
            latest_event = next(iter(self.events.find(
                {"type": {"$exists": True}}, {"seq": 1}
            ).sort("seq", -1).limit(1)), None)
            revision = latest_event["seq"] if latest_event else 0
            self.events.find_one_and_update(
                {"_id": self.COUNTER_ID},
                {"$setOnInsert": {"next_seq": revision}},
                upsert=True,
                return_document=ReturnDocument.AFTER,
            )
            self._revision = revision
            latest_history_event = self._latest_workspace_history_event()
            if latest_history_event:
                self._head_checkpoint_seq = (
                    latest_history_event["seq"]
                    if latest_history_event["type"] == "workspace.checkpoint"
                    else latest_history_event["data"]["checkpoint_seq"]
                )
            self._load_workspace_state()
            self._loaded = True
            self._load_error = None
        except PyMongoError as error:
            self._load_error = error
            self._loaded = False
            self._revision = 0

    def _load_workspace_state(self) -> None:
        meta = self.workspace.find_one({"_id": self.WORKSPACE_META_ID})
        if meta and meta.get("initialized"):
            self._workspace_generation = meta.get("generation", 1)
            self._file_revision = meta.get("file_revision", 0)
            self._head_checkpoint_seq = meta.get("head_checkpoint_seq", self._head_checkpoint_seq)
            if meta.get("head_event_seq", self._revision) < self._revision:
                latest_history_event = self._latest_workspace_history_event()
                if latest_history_event:
                    self._head_checkpoint_seq = (
                        latest_history_event["seq"]
                        if latest_history_event["type"] == "workspace.checkpoint"
                        else latest_history_event["data"]["checkpoint_seq"]
                    )
            self._workspace_write(lambda: self.workspace.delete_many({"generation": {"$ne": self._workspace_generation}}))
            return
        latest_file = self.workspace.find_one(
            {"file_id": {"$exists": True}}, {"generation": 1}, sort=[("generation", -1)]
        )
        self._workspace_generation = latest_file.get("generation", 1) if latest_file else 1
        latest_file_revision = self.workspace.find_one(
            {"generation": self._workspace_generation}, {"revision": 1}, sort=[("revision", -1)]
        )
        self._file_revision = latest_file_revision.get("revision", 0) if latest_file_revision else 0
        self._persist_workspace_meta()

    def _latest_workspace_history_event(self) -> dict[str, Any] | None:
        events = self.events.find(
            {"type": {"$in": ["workspace.checkpoint", "workspace.restore"]}},
            {"seq": 1, "type": 1, "data.checkpoint_seq": 1},
        ).sort("seq", -1).limit(1)
        return next(iter(events), None)

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
        self._persist_workspace_meta()
        return self._file_revision

    def _workspace_write(self, operation, *, duplicate_is_conflict: bool = False) -> None:
        try:
            operation()
        except DuplicateKeyError as error:
            key_pattern = (error.details or {}).get("keyPattern", {})
            if duplicate_is_conflict and set(key_pattern) == {"generation", "name"}:
                raise FileNameConflictError("file name already exists") from error
            self._loaded = False
            self._load_error = error
            raise FileStoreUnavailableError("workspace file store is unavailable") from error
        except PyMongoError as error:
            self._loaded = False
            self._load_error = error
            raise FileStoreUnavailableError("workspace file store is unavailable") from error

    def _workspace_read(self, operation):
        try:
            return operation()
        except PyMongoError as error:
            self._loaded = False
            self._load_error = error
            raise FileStoreUnavailableError("workspace file store is unavailable") from error

    def _current_files(self, include_content: bool = True) -> list[dict[str, Any]]:
        projection = None if include_content else {"content": 0}
        documents = self._workspace_read(lambda: self.workspace.find(
            {"generation": self._workspace_generation}, projection
        ))
        return [
            {key: value for key, value in item.items() if key not in ("_id", "generation")}
            for item in documents if item.get("file_id")
        ]

    def _ensure_loaded(self) -> None:
        if not self._loaded:
            self._load()
        if not self._loaded:
            raise FileStoreUnavailableError("workspace file store is unavailable") from self._load_error

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
        if event_type in ("workspace.checkpoint", "workspace.restore"):
            self._persist_workspace_meta()
        return {key: value for key, value in event.items() if key != "_id"}

    def _apply(self, event: dict[str, Any]) -> None:
        if event.get("version") != 1:
            raise RuntimeError("unsupported workspace file event version")
        if event["seq"] <= self._revision:
            raise RuntimeError("workspace file event sequence is not strictly increasing")
        data = event["data"]
        event_type = event["type"]
        if event_type == "workspace.checkpoint":
            data.setdefault("parent_seq", self._head_checkpoint_seq)
            self._head_checkpoint_seq = event["seq"]
        elif event_type == "workspace.restore":
            self._head_checkpoint_seq = data["checkpoint_seq"]
        else:
            raise RuntimeError("unsupported workspace file event type")
        self._revision = event["seq"]

    def _require_file(self, file_id: str) -> dict[str, Any]:
        document = self._workspace_read(lambda: self.workspace.find_one({
            "_id": self._workspace_id(file_id),
            "generation": self._workspace_generation,
        }))
        if document is None:
            raise FileMissingError
        return {key: value for key, value in document.items() if key not in ("_id", "generation")}

    @staticmethod
    def _check_revision(file: dict[str, Any], expected_revision: int) -> None:
        if file["revision"] != expected_revision:
            raise FileConflictError

    def _check_unique_file_name(self, name: str, exclude_file_id: str | None = None) -> None:
        if any(
            file["name"] == name and file["file_id"] != exclude_file_id
            for file in self._current_files(include_content=False)
        ):
            raise FileNameConflictError(f"file name already exists: {name}")

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _copy(file: dict[str, Any], include_content: bool = True) -> dict[str, Any]:
        result = dict(file)
        result["permissions"] = normalize_permissions(result.get("permissions"))
        if not include_content:
            result.pop("content", None)
        return result
