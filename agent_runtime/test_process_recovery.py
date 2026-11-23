"""Startup recovery preserves history when the private Redis state disappears."""
import copy
import json
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from pymongo import ReturnDocument
from redis.exceptions import BusyLoadingError, ConnectionError

from test_support import MemoryRedis
from process_repository import PROCESSTABLE, TERMINAL_INDEX, TERMINAL_SESSIONS, TERMINAL_STATUSES
from process_recovery import LOSS_REASON, reconcile_lost_processes
from redis_client import REDIS_PUBLIC_DB


class LostProcessRecoveryTest(unittest.TestCase):
    def setUp(self):
        self.redis = MemoryRedis()
        self.public = self.redis.with_db(REDIS_PUBLIC_DB)
        self.logs = MagicMock()
        self.stamp = datetime(2026, 11, 21, 1, tzinfo=timezone.utc)
        self.documents = {}
        self.logs.find.side_effect = lambda query: [copy.deepcopy(p) for p in self.documents.values()
            if p["status"] == "lost" or p["status"] not in TERMINAL_STATUSES and not p.get("finished_at")]
        self.logs.find_one_and_update.side_effect = self.update
        self.runs = MagicMock()
        patcher = patch("process_recovery.record_process_workflow_run", self.runs)
        patcher.start()
        self.addCleanup(patcher.stop)

    def add(self, pid, status="running", **extra):
        p = {"_id": pid, "process_id": pid, "process_type": "workflow", "status": status,
             "workflow_name": "Root.flow", "root_process_id": "root", "terminal_id": "session",
             "invocation_id": "invocation-" + pid, "start_time": self.stamp,
             "observed_at": self.stamp + timedelta(seconds=2), "input": {"text": "keep input"},
             "nodes": [{"node_id": "llm", "started_at": self.stamp}],
             "events": [{"event": "started", "status": status, "timestamp": self.stamp.isoformat()}],
             "wait_for": {"kind": "process_exit", "process_id": "child"}, **extra}
        self.documents[pid] = copy.deepcopy(p)
        return p

    def update(self, query, change, **kwargs):
        p = self.documents[query["_id"]]
        if any(p.get(key) != value for key, value in query.items()):
            return None
        p.update(copy.deepcopy(change["$set"]))
        p.setdefault("events", []).append(copy.deepcopy(change["$push"]["events"]))
        return copy.deepcopy(p)

    def test_empty_kernel_marks_entire_missing_tree_lost_and_preserves_history(self):
        original = [self.add("root"), self.add("child", parent_process_id="root", workflow_name="Child.flow"),
                    self.add("terminal", process_type="terminal", parent_process_id="child")]
        self.redis.hset(TERMINAL_INDEX, "session", "terminal")
        reconcile_lost_processes(self.redis, self.logs)

        for old in original:
            p = self.documents[old["process_id"]]
            self.assertEqual(p["status"], "lost")
            self.assertIsInstance(p["finished_at"], datetime)
            self.assertIsNone(p["wait_for"])
            self.assertEqual(p["nodes"], old["nodes"])
            self.assertEqual(p["input"], old["input"])
            self.assertEqual(p["observed_at"], old["observed_at"])
            self.assertEqual(p["events"][:-1], old["events"])
            self.assertEqual(p["events"][-1]["event"], "lost")
            self.assertEqual(p["events"][-1]["timestamp"], p["finished_at"].isoformat())
            self.assertNotIn("total_duration_ms", p)
        self.assertFalse(self.redis.hgetall(PROCESSTABLE))
        self.assertFalse(self.redis.hget(TERMINAL_INDEX, "session"))
        session = json.loads(self.public.hget(TERMINAL_SESSIONS, "session"))
        self.assertEqual(session["status"], "closed")
        self.assertEqual(session["workflow_status"], "lost")
        self.assertEqual(session["workflow_name"], "Root.flow")
        self.assertEqual(session["closed_at"], self.documents["root"]["finished_at"].isoformat())
        self.assertEqual(self.runs.call_count, 2)
        for call in self.runs.call_args_list:
            run = call.args[0]
            self.assertEqual(run["run_id"], "invocation-" + run["process_id"])
            self.assertEqual(run["status"], "lost")
            self.assertEqual(run["finished_at"], self.documents[run["process_id"]]["finished_at"])
            self.assertIsNone(run["duration_ms"])
        self.assertEqual(self.logs.find_one_and_update.call_args.kwargs["return_document"], ReturnDocument.AFTER)

    def test_partial_loss_keeps_surviving_process_and_its_session(self):
        root = self.add("root", status="blocked")
        self.add("child", parent_process_id="root")
        self.redis.hset(PROCESSTABLE, "root", json.dumps({"process_id": "root", "status": "blocked", "terminal_id": "session"}))
        self.public.hset(TERMINAL_SESSIONS, "session", '{"status":"open"}')
        reconcile_lost_processes(self.redis, self.logs)
        self.assertEqual(self.documents["root"], root)
        self.assertEqual(self.documents["child"]["status"], "lost")
        self.assertEqual(self.public.hget(TERMINAL_SESSIONS, "session"), '{"status":"open"}')
        self.assertEqual(self.logs.find_one_and_update.call_count, 1)

    def test_new_active_run_on_same_terminal_is_not_closed_by_old_loss(self):
        self.add("root")
        self.redis.hset(PROCESSTABLE, "new-root", json.dumps({"process_id": "new-root", "status": "ready", "terminal_id": "session"}))
        self.public.hset(TERMINAL_SESSIONS, "session", '{"status":"open"}')
        reconcile_lost_processes(self.redis, self.logs)
        self.assertEqual(self.public.hget(TERMINAL_SESSIONS, "session"), '{"status":"open"}')

    def test_newer_completed_run_on_same_terminal_keeps_its_session(self):
        self.add("root")
        newer = {"process_id": "new-root", "root_process_id": "new-root", "status": "completed",
                 "terminal_id": "session", "start_time": (self.stamp + timedelta(hours=1)).isoformat()}
        self.redis.hset(PROCESSTABLE, "new-root", json.dumps(newer))
        self.public.hset(TERMINAL_SESSIONS, "session", '{"status":"closed","workflow_status":"completed"}')
        reconcile_lost_processes(self.redis, self.logs)
        self.assertEqual(json.loads(self.public.hget(TERMINAL_SESSIONS, "session"))["workflow_status"], "completed")

    def test_multiple_missing_runs_use_latest_root_metadata_independent_of_scan_order(self):
        self.add("new-root", root_process_id="new-root", workflow_name="New.flow",
                 start_time=self.stamp + timedelta(hours=1))
        self.add("root")
        reconcile_lost_processes(self.redis, self.logs)
        session = json.loads(self.public.hget(TERMINAL_SESSIONS, "session"))
        self.assertEqual(session["workflow_name"], "New.flow")
        self.assertEqual(session["start_time"], (self.stamp + timedelta(hours=1)).isoformat())
        self.assertEqual(session["closed_at"], self.documents["new-root"]["finished_at"].isoformat())

    def test_replay_keeps_finish_timestamp_and_events_and_retries_derived_records(self):
        self.add("root")
        self.runs.side_effect = RuntimeError("workflow log temporarily offline")
        with self.assertRaises(RuntimeError):
            reconcile_lost_processes(self.redis, self.logs)
        saved = copy.deepcopy(self.documents["root"])
        self.runs.side_effect = None
        reconcile_lost_processes(self.redis, self.logs)
        reconcile_lost_processes(self.redis, self.logs)
        self.assertEqual(self.documents["root"], saved)
        self.assertEqual(self.logs.find_one_and_update.call_count, 1)
        self.assertEqual(self.runs.call_count, 3)
        self.assertEqual(json.loads(self.public.hget(TERMINAL_SESSIONS, "session"))["workflow_status"], "lost")

    def test_redis_errors_and_loading_are_not_treated_as_empty_state(self):
        self.add("root")
        for error in (ConnectionError("offline"), BusyLoadingError("loading")):
            with self.subTest(error=type(error).__name__):
                client = MagicMock()
                client.hgetall.side_effect = error
                with self.assertRaises(type(error)):
                    reconcile_lost_processes(client, self.logs)
        self.logs.find.assert_not_called()
        self.logs.find_one_and_update.assert_not_called()

    def test_recheck_failure_does_not_mark_process_lost(self):
        self.add("root")
        with patch.object(self.redis, "hexists", side_effect=ConnectionError("offline")):
            with self.assertRaises(ConnectionError):
                reconcile_lost_processes(self.redis, self.logs)
        self.logs.find_one_and_update.assert_not_called()

    def test_changed_observation_is_not_overwritten(self):
        self.add("root")
        self.logs.find_one_and_update.side_effect = None
        self.logs.find_one_and_update.return_value = None
        reconcile_lost_processes(self.redis, self.logs)
        query = self.logs.find_one_and_update.call_args.args[0]
        self.assertEqual(query["observed_at"], self.documents["root"]["observed_at"])
        self.runs.assert_not_called()
        self.assertFalse(self.public.hgetall(TERMINAL_SESSIONS))

    def test_closed_history_is_excluded_and_missing_legacy_invocation_uses_process_id(self):
        for status in ("completed", "failed", "terminated"):
            self.add(status, status=status)
        self.add("root", invocation_id=None)
        reconcile_lost_processes(self.redis, self.logs)
        self.assertEqual(self.logs.find_one_and_update.call_count, 1)
        query = self.logs.find.call_args.args[0]
        self.assertEqual(query["$or"][0]["status"]["$nin"], sorted(TERMINAL_STATUSES))
        self.assertEqual(self.runs.call_args.args[0]["run_id"], "root")
        for status in ("completed", "failed", "terminated"):
            self.assertEqual(self.documents[status]["status"], status)


if __name__ == "__main__":
    unittest.main()
