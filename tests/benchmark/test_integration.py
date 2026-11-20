"""Real Redis/Mongo + runtime + ALFWorld acceptance tests, opt in via Compose."""
import os
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import requests
from redis.exceptions import RedisError
from benchmark_common.models import JobConfig
from benchmark_common.store import Store, now


@unittest.skipUnless(os.getenv("BENCHMARK_INTEGRATION") == "1", "requires isolated acceptance stack")
class StorageIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.parent = Store()
        self.store = Store(self.parent.db.client["benchmark_contract_" + uuid4().hex], self.parent.redis)
        self.store.stream = "benchmark:test:" + uuid4().hex
        self.store.indexes()

    def tearDown(self):
        self.parent.close()

    def create(self):
        return self.store.create(JobConfig(workflow_file_id="flow").model_dump(), "test")

    def test_concurrent_claim_only_has_one_owner(self):
        job = self.create()
        with ThreadPoolExecutor(2) as pool:
            results = list(pool.map(lambda worker: self.store.claim(job["job_id"], worker), ["a", "b"]))
        self.assertEqual(sum(result is not None for result in results), 1)
        owner = next(result["worker_id"] for result in results if result)
        other = "b" if owner == "a" else "a"
        self.assertFalse(self.store.update_running(job["job_id"], other, {"status": "completed"}))
        self.assertTrue(self.store.update_running(job["job_id"], owner, {"status": "completed"}))
        self.assertIsNone(self.store.claim(job["job_id"], other))

    def test_failed_dispatch_retries_persisted_job(self):
        job = self.create()
        with patch.object(self.store.redis, "xadd", side_effect=RedisError("offline")):
            with self.assertRaises(RedisError):
                self.store.dispatch()
        saved = self.store.get(job["job_id"])
        self.assertEqual(saved["status"], "queued")
        self.assertIn("offline", saved["dispatch_error"])
        self.store.jobs.update_one({"job_id": job["job_id"]}, {"$set": {"dispatch_after": now()}})
        self.store.dispatch()
        messages = self.store.redis.xrange(self.store.stream)
        self.assertEqual([item[1]["job_id"] for item in messages], [job["job_id"]])
        self.assertNotIn("dispatch_error", self.store.get(job["job_id"]))

    def test_stale_worker_retains_trace_and_cannot_resume(self):
        job = self.create()
        self.store.claim(job["job_id"], "old")
        self.store.episodes.insert_one({"job_id": job["job_id"], "index": 0, "status": "running"})
        self.store.append(job["job_id"], "old", 0, {"direction": "action", "text": "look"})
        self.store.jobs.update_one({"job_id": job["job_id"]},
                                  {"$set": {"lease_until": now() - timedelta(seconds=1)}})
        self.assertFalse(self.store.heartbeat("old", job["job_id"]))
        self.store.reap()
        self.assertEqual(self.store.get(job["job_id"])["status"], "failed")
        self.assertEqual(self.store.events.count_documents({"job_id": job["job_id"]}), 1)
        self.assertEqual(self.store.episodes.find_one({"job_id": job["job_id"]})["status"], "interrupted")
        self.assertIsNone(self.store.claim(job["job_id"], "new"))
        with self.assertRaisesRegex(RuntimeError, "lease lost"):
            self.store.append(job["job_id"], "old", 0, {"direction": "action", "text": "look"})


@unittest.skipUnless(os.getenv("BENCHMARK_INTEGRATION") == "1", "requires isolated acceptance stack")
class FullStackTests(unittest.TestCase):
    base = "http://benchmark_webui:8085"

    def request(self, method, path, **kwargs):
        response = requests.request(method, self.base + path, timeout=15, **kwargs)
        response.raise_for_status()
        return response.json()

    def wait_job(self, job_id):
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            job = self.request("GET", "/api/jobs/" + job_id)
            if job["status"] in ("completed", "failed"):
                return job
            time.sleep(0.2)
        self.fail("Benchmark job did not finish: " + str(job))

    def test_webui_queue_worker_runtime_and_mongo(self):
        runtime = os.environ["AAGENT_API_URL"]
        response = requests.post(runtime + "/api/files", json={"name": "benchmark-look-" + uuid4().hex[:8] + ".flow",
            "content": Path("/examples/alfworld-look.flow").read_text()}, timeout=15)
        response.raise_for_status()
        workflow = response.json()["file_id"]
        options = self.request("GET", "/api/options")
        self.assertIn(workflow, [item["file_id"] for item in options["workflows"]])
        created = self.request("POST", "/api/jobs", json={"workflow_file_id": workflow,
            "name": "Real ALFWorld acceptance", "episodes": 2, "max_steps": 2,
            "action_timeout": 20, "startup_timeout": 20})
        self.assertIn(created["status"], ("queued", "running"))
        job_id = created["job_id"]
        # Repeated delivery while running must not create extra environments.
        store = Store()
        try:
            for _ in range(3):
                store.redis.xadd(store.stream, {"job_id": job_id})
            job = self.wait_job(job_id)
            self.assertEqual(job["status"], "completed", job)
            self.assertEqual(job["summary"], {"requested": 2, "completed": 2,
                "successes": 0, "errors": 0, "success_rate": 0})
            self.assertIn("alfworld", job["metadata"]["versions"])
            episodes = self.request("GET", "/api/jobs/" + job_id + "/episodes")["items"]
            self.assertEqual(len(episodes), 2)
            self.assertEqual(len({item["terminal_id"] for item in episodes}), 2)
            self.assertEqual(len({item["gamefile"] for item in episodes}), 2)
            self.assertTrue(all(item["status"] == "max_steps" and item["steps"] == 2 for item in episodes))
            # Small pages exercise the public cursor, including empty polling.
            records, cursor = [], 0
            while True:
                page = self.request("GET", "/api/jobs/" + job_id + "/events",
                                    params={"after": cursor, "limit": 2})
                records.extend(page["items"])
                self.assertGreaterEqual(page["next_cursor"], cursor)
                cursor = page["next_cursor"]
                if not page["has_more"]:
                    break
            self.assertEqual(len(records), 12)
            self.assertEqual(len({item["seq"] for item in records}), 12)
            actions = [item for item in records if item["direction"] == "action"]
            self.assertEqual([item["text"] for item in actions], ["look"] * 4)
            filtered = self.request("GET", "/api/jobs/" + job_id + "/events", params={"episode": 1})
            self.assertEqual(len(filtered["items"]), 6)
            self.assertTrue(all(item["episode_index"] == 1 for item in filtered["items"]))
            self.assertEqual(store.events.count_documents({"job_id": job_id}), 12)
            self.assertEqual(store.episodes.count_documents({"job_id": job_id}), 2)
            deadline = time.monotonic() + 15
            ids = {item["terminal_id"] for item in episodes}
            while time.monotonic() < deadline:
                sessions = requests.get(runtime + "/api/terminal/sessions", timeout=10).json()["sessions"]
                selected = [item for item in sessions if item["terminal_id"] in ids]
                if len(selected) == 2 and all(item["status"] == "closed" for item in selected):
                    break
                time.sleep(0.1)
            self.assertEqual(len(selected), 2)
            self.assertTrue(all(item["workflow_status"] == "completed" for item in selected), selected)
            print("ACCEPTANCE_JOB=" + job_id, flush=True)
        finally:
            store.close()

    def test_single_container_runs_two_jobs_and_queues_excess(self):
        runtime = os.environ["AAGENT_API_URL"]
        response = requests.post(runtime + "/api/files", json={
            "name": "parallel-look-" + uuid4().hex[:8] + ".flow",
            "content": Path("/examples/alfworld-look.flow").read_text()}, timeout=15)
        response.raise_for_status()
        workflow = response.json()["file_id"]
        created = [self.request("POST", "/api/jobs", json={
            "workflow_file_id": workflow, "name": "Concurrent test " + str(index),
            "episodes": 1, "max_steps": 8, "seed": 42,
            "action_timeout": 20, "startup_timeout": 20}) for index in range(3)]
        ids = [job["job_id"] for job in created]
        deadline = time.monotonic() + 120
        observed_parallel = observed_backpressure = False
        while time.monotonic() < deadline:
            # One Mongo snapshot avoids counting a completed slot twice while
            # issuing sequential HTTP requests during a scheduling transition.
            store = Store()
            try:
                snapshot = list(store.jobs.find({"job_id": {"$in": ids}}))
            finally:
                store.close()
            running = sum(job["status"] == "running" for job in snapshot)
            queued = sum(job["status"] == "queued" for job in snapshot)
            self.assertLessEqual(running, 2, snapshot)
            observed_parallel |= running == 2
            observed_backpressure |= running == 2 and queued == 1
            if all(job["status"] in ("completed", "failed") for job in snapshot):
                break
            time.sleep(0.1)
        else:
            self.fail("Concurrent tests did not finish")
        self.assertTrue(observed_parallel, "Tests ran serially")
        self.assertTrue(observed_backpressure, "Excess tests were not left queued")
        jobs = [self.request("GET", "/api/jobs/" + job_id) for job_id in ids]
        self.assertTrue(all(job["status"] == "completed" for job in jobs), jobs)
        self.assertEqual(len({job["worker_id"].rsplit(":process-", 1)[0] for job in jobs}), 1)
        self.assertEqual(len({job["worker_id"] for job in jobs}), 2)
        events = [self.request("GET", "/api/jobs/" + job_id + "/events")["items"] for job_id in ids]
        episodes = [self.request("GET", "/api/jobs/" + job_id + "/episodes")["items"][0] for job_id in ids]
        self.assertEqual(len({episode["terminal_id"] for episode in episodes}), 3)
        self.assertTrue(all(episode["steps"] == 8 for episode in episodes))
        # Same seed must reproduce the game and observations even when the
        # environments run in different processes.
        self.assertEqual(len({episode["gamefile"] for episode in episodes}), 1)
        observations = [[event["message"]["text"] for event in trace
                         if event["direction"] == "observation"] for trace in events]
        self.assertEqual(observations[0], observations[1])
        self.assertEqual(observations[0], observations[2])
        for trace in events:
            self.assertEqual(len(trace), 18)
            self.assertEqual([event["seq"] for event in trace], list(range(1, 19)))
            self.assertEqual(sum(event["direction"] == "action" for event in trace), 8)
        ordered = sorted(events, key=lambda trace: trace[0]["created_at"])
        self.assertLess(ordered[1][0]["created_at"], ordered[0][-1]["created_at"],
                        "ALFWorld interaction did not overlap across processes")
        options = self.request("GET", "/api/options")
        online = [worker for worker in options["workers"] if worker["online"]]
        self.assertEqual(len(online), 2)
        self.assertEqual(len({worker["instance_id"] for worker in online}), 1)
        self.assertEqual({worker["slot"] for worker in online}, {1, 2})
        self.assertEqual(len({worker["pid"] for worker in online}), 2)
        print("CONCURRENT_JOBS=" + ",".join(ids), flush=True)

    def test_validation_and_static_assets(self):
        for body in ({"workflow_file_id": "missing", "episodes": 0},
                     {"workflow_file_id": "missing", "action_timeout": 0}):
            response = requests.post(self.base + "/api/jobs", json=body, timeout=10)
            self.assertEqual(response.status_code, 422)
        response = requests.post(self.base + "/api/jobs", json={"workflow_file_id": "missing"}, timeout=10)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(requests.get(self.base + "/api/jobs/missing", timeout=10).status_code, 404)
        response = requests.get(self.base, timeout=10)
        self.assertEqual(response.status_code, 200)
        self.assertIn('id="job-form"', response.text)
        self.assertIn('id="trace"', response.text)
        for asset in ("/static/app.js", "/static/style.css"):
            self.assertEqual(requests.get(self.base + asset, timeout=10).status_code, 200)


if __name__ == "__main__":
    unittest.main()
