"""Spawn isolation, bounded process execution, leases and shutdown."""
import argparse
import multiprocessing
import os
import signal
import threading
import time
import unittest
from functools import partial
from unittest.mock import Mock, patch

from benchmark_worker.main import Worker, WorkerPool, concurrency_value


# Spawn targets/factories must be importable; no inherited mocks or DB sockets.
class ProcessStore:
    def __init__(self, events, fail_indexes=False):
        self.events = events
        self.fail_indexes = fail_indexes
        self.pid = os.getpid()
        self.events.put(("open", self.pid))

    def indexes(self):
        self.events.put(("indexes", self.pid))
        if self.fail_indexes:
            raise RuntimeError("connect failed")

    def close(self):
        self.events.put(("close", self.pid))


class ProcessWorker(Worker):
    def __init__(self, *args, barrier, mode="normal", **kwargs):
        super().__init__(*args, **kwargs)
        self.barrier = barrier
        self.mode = mode

    def run(self):
        try:
            if self.mode == "hung" and self.slot == 2:
                signal.signal(signal.SIGTERM, signal.SIG_IGN)
            self.store.events.put(("worker", os.getpid(), self.store.pid,
                                   self.worker_id, self.instance_id, self.slot))
            self.barrier.wait(timeout=15)
            if self.mode in ("failure", "hung"):
                if self.slot == 1:
                    raise RuntimeError("execution process failed")
                if self.mode == "hung":
                    while True:
                        threading.Event().wait(10)
                if not self.stopping.wait(15):
                    raise AssertionError("other processes were not stopped")
            else:
                self.stopping.set()
        finally:
            self.store.close()


class ConcurrencyTests(unittest.TestCase):
    def pool(self, concurrency, mode="normal", **kwargs):
        pool = WorkerPool(concurrency, **kwargs)
        events = pool.context.Queue()
        self.addCleanup(events.join_thread)
        self.addCleanup(events.close)
        pool.store_factory = partial(ProcessStore, events)
        pool.worker_factory = partial(ProcessWorker,
                                      barrier=pool.context.Barrier(concurrency), mode=mode)
        return pool, events

    def test_concurrency_limits(self):
        self.assertEqual(concurrency_value("4"), 4)
        self.assertEqual(concurrency_value(1), 1)
        for value in (0, -1, 33, True, 1.5, "x"):
            with self.subTest(value=value), self.assertRaises(argparse.ArgumentTypeError):
                concurrency_value(value)

    def test_slots_run_in_independent_spawn_processes(self):
        pool, events = self.pool(3)
        self.assertEqual(pool.context.get_start_method(), "spawn")
        pool.run()
        records = [events.get(timeout=5) for _ in range(12)]
        workers = [record for record in records if record[0] == "worker"]
        pids = {record[1] for record in workers}
        self.assertEqual(len(pids), 3)
        self.assertNotIn(os.getpid(), pids)
        self.assertTrue(all(record[1] == record[2] for record in workers))
        self.assertEqual({record[4] for record in workers}, {pool.instance_id})
        self.assertEqual({record[5] for record in workers}, {1, 2, 3})
        self.assertEqual(len({record[3] for record in workers}), 3)
        for operation in ("open", "indexes", "close"):
            self.assertCountEqual([record[1] for record in records if record[0] == operation], pids)
        self.assertTrue(pool.stopping.is_set())

    def test_initialization_failure_closes_child_store(self):
        pool, events = self.pool(1)
        pool.store_factory = partial(ProcessStore, events, fail_indexes=True)
        with self.assertRaisesRegex(RuntimeError, "exit code 1"):
            pool.run()
        records = [events.get(timeout=5) for _ in range(3)]
        self.assertEqual([record[0] for record in records], ["open", "indexes", "close"])
        self.assertNotEqual(records[0][1], os.getpid())
        self.assertTrue(pool.stopping.is_set())

    def test_unexpected_process_failure_stops_other_slots(self):
        pool, events = self.pool(2, mode="failure")
        with self.assertRaisesRegex(RuntimeError, "exit code 1"):
            pool.run()
        records = [events.get(timeout=5) for _ in range(8)]
        self.assertEqual(sum(record[0] == "close" for record in records), 2)
        self.assertTrue(pool.stopping.is_set())

    def test_hung_child_is_killed_within_shutdown_deadline(self):
        pool, events = self.pool(2, mode="hung", shutdown_timeout=0.3)
        before = {child.pid for child in multiprocessing.active_children()}
        started = time.monotonic()
        with self.assertLogs("benchmark_worker", level="WARNING"):
            with self.assertRaisesRegex(RuntimeError, "exit code 1"):
                pool.run()
        records = [events.get(timeout=5) for _ in range(7)]
        pids = {record[1] for record in records if record[0] == "worker"}
        self.assertEqual(len(pids), 2)
        self.assertLess(time.monotonic() - started, 15)
        self.assertEqual({child.pid for child in multiprocessing.active_children()} - before, set())

    def test_partial_startup_failure_stops_started_children(self):
        pool, _ = self.pool(2)
        create_process = pool.context.Process
        first = create_process(target=pool.stopping.wait)
        with patch.object(pool.context, "Process", side_effect=[first, RuntimeError("start failed")]):
            with self.assertRaisesRegex(RuntimeError, "start failed"):
                pool.run()
        self.assertTrue(pool.stopping.is_set())
        self.assertNotIn(first, multiprocessing.active_children())

    def test_one_lost_lease_does_not_stop_another_slot(self):
        stopping = multiprocessing.get_context("spawn").Event()
        first = Worker(Mock(), instance_id="one-container", slot=1, concurrency=2, stopping=stopping)
        second = Worker(Mock(), instance_id="one-container", slot=2, concurrency=2, stopping=stopping)
        first.active_job, second.active_job = "job-a", "job-b"
        first.lease_lost.set()
        with self.assertRaisesRegex(RuntimeError, "lease"):
            first.check()
        second.check()
        stopping.set()
        with self.assertRaisesRegex(RuntimeError, "shutting down"):
            second.check()

    def test_heartbeat_reports_slot_and_instance(self):
        store = Mock()
        worker = Worker(store, instance_id="container", slot=2, concurrency=4)
        worker.dataset_ready = Mock(return_value=True)
        worker.heartbeat("job")
        store.heartbeat.assert_called_once_with("container:process-2", "job", True,
                                               instance_id="container", slot=2, concurrency=4)


if __name__ == "__main__":
    unittest.main()
