"""Run independent ALFWorld tests concurrently in one worker container."""
import argparse
import logging
import multiprocessing
import os
import signal
import socket
import threading
import time
from multiprocessing.connection import wait
from importlib.metadata import version
from pathlib import Path
from uuid import uuid4

from alfworld_runner.client import TerminalClient
from alfworld_runner.environment import download_data, make_environment
from alfworld_runner.runner import run_episode
from benchmark_common.models import JobConfig, summarize
from benchmark_common.store import GROUP, Store, now

log = logging.getLogger("benchmark_worker")
CONFIG = str(Path(__file__).parents[1] / "alfworld_runner" / "config.yaml")


class Worker:
    def __init__(self, store, env_factory=make_environment, client_factory=TerminalClient,
                 *, instance_id=None, slot=1, concurrency=1, stopping=None):
        self.store = store
        self.env_factory = env_factory
        self.client_factory = client_factory
        self.instance_id = instance_id or socket.gethostname() + "-" + uuid4().hex[:8]
        self.slot = slot
        self.concurrency = concurrency
        self.worker_id = f"{self.instance_id}:process-{slot}"
        self.stopping = stopping if stopping is not None else threading.Event()
        self.active_job = None
        self.lease_lost = threading.Event()

    def dataset_ready(self):
        return (Path(os.getenv("ALFWORLD_DATA", "/data/alfworld")) / ".text-data-0.4.2.complete").exists()

    def check(self):
        if self.stopping.is_set():
            raise RuntimeError("Worker is shutting down")
        if self.lease_lost.is_set():
            raise RuntimeError("Worker lost its benchmark job lease")

    def heartbeat(self, job_id=None):
        return self.store.heartbeat(
            self.worker_id, job_id, self.dataset_ready(),
            instance_id=self.instance_id, slot=self.slot, concurrency=self.concurrency)

    def keepalive(self, done):
        while not done.wait(5):
            job_id = self.active_job
            try:
                if not self.heartbeat(job_id):
                    if job_id == self.active_job:
                        self.lease_lost.set()
            except Exception:
                # Fail closed when Mongo cannot confirm ownership.
                if job_id and job_id == self.active_job:
                    self.lease_lost.set()
                log.exception("Benchmark heartbeat failed")
            try:
                self.store.maintenance()
            except Exception:
                # A temporary Redis failure must not interrupt an active test.
                log.exception("Benchmark dispatch maintenance failed")

    def execute(self, job):
        job_id = job["job_id"]
        config = JobConfig.model_validate(job["config"])
        env = client = None
        results = []
        try:
            self.check()
            env, games = self.env_factory(CONFIG, config.split, config.max_steps, config.seed)
            if config.episodes > len(games):
                raise ValueError(f"Requested {config.episodes} episodes but split contains {len(games)} games")
            versions = {name: version(name) for name in ("alfworld", "textworld", "numpy")}
            self.store.update_running(job_id, self.worker_id, {"metadata": {
                "versions": versions, "game_files": list(games), "environment": "AlfredTWEnv"}})
            client = self.client_factory(os.getenv("AAGENT_API_URL", "http://webui_py:8081"),
                                         check=self.check)
            for index in range(config.episodes):
                self.check()
                episode_id = uuid4().hex
                episode = {"job_id": job_id, "index": index, "episode_id": episode_id,
                           "terminal_id": "alfworld-" + episode_id, "status": "running",
                           "steps": 0, "started_at": now()}
                self.store.episodes.insert_one(episode)
                self.store.update_running(job_id, self.worker_id, {"current_episode": index})

                def journal(record):
                    self.check()
                    self.store.append(job_id, self.worker_id, index, record)
                    if record["direction"] == "observation":
                        message = record["message"]
                        self.store.episodes.update_one({"job_id": job_id, "index": index},
                            {"$set": {"steps": message["step"], "score": message["score"],
                                      "success": message["success"]}})

                result = run_episode(env, client, config.workflow_file_id, config.inputs,
                                     config.max_steps, config.action_timeout, config.startup_timeout,
                                     config.admissible_commands, journal, episode_id=episode_id)
                results.append(result)
                self.store.episodes.update_one({"job_id": job_id, "index": index},
                                               {"$set": dict(result, finished_at=now())})
                self.store.update_running(job_id, self.worker_id,
                                          {"summary": summarize(results, config.episodes)})
                if result["status"] == "error":
                    raise RuntimeError(result.get("error", "Episode failed"))
            self.store.update_running(job_id, self.worker_id, {"status": "completed", "finished_at": now()})
        except Exception as error:
            log.exception("Benchmark %s failed", job_id)
            self.store.update_running(job_id, self.worker_id, {
                "status": "failed", "error": f"{type(error).__name__}: {error}",
                "summary": summarize(results, config.episodes), "finished_at": now()})
            self.store.episodes.update_many({"job_id": job_id, "status": "running"},
                {"$set": {"status": "interrupted", "finished_at": now(), "error": str(error)}})
        finally:
            for resource in (client, env):
                if resource is not None:
                    try:
                        resource.close()
                    except Exception:
                        log.exception("Failed to close benchmark resource")

    def handle(self, message_id, fields):
        job_id = fields.get("job_id")
        job = self.store.claim(job_id, self.worker_id) if job_id else None
        if job:
            self.active_job = job_id
            self.lease_lost.clear()
            try:
                self.execute(job)
            finally:
                self.active_job = None
        # A duplicate notification must never execute a running/completed job.
        self.store.redis.xack(self.store.stream, GROUP, message_id)
        self.store.redis.xdel(self.store.stream, message_id)

    def run(self):
        done = threading.Event()
        heartbeat = threading.Thread(target=self.keepalive, args=(done,), daemon=True)
        heartbeat.start()
        try:
            while not self.stopping.is_set():
                try:
                    self.store.ensure_group()
                    self.heartbeat()
                    self.store.maintenance()
                    # Recover abandoned notifications. Mongo claims prevent
                    # re-execution; stale running jobs are failed, never resumed.
                    pending = self.store.redis.xautoclaim(self.store.stream, GROUP, self.worker_id,
                                                         min_idle_time=60000, start_id="0-0", count=1)
                    messages = pending[1]
                    if not messages:
                        pages = self.store.redis.xreadgroup(GROUP, self.worker_id,
                            {self.store.stream: ">"}, count=1, block=1000)
                        messages = pages[0][1] if pages else []
                    for message_id, fields in messages:
                        if self.stopping.is_set():
                            break
                        self.handle(message_id, fields)
                except Exception:
                    log.exception("Benchmark queue iteration failed")
                    self.stopping.wait(2)
        finally:
            done.set()
            heartbeat.join(timeout=10)
            try:
                self.store.offline(self.worker_id)
            except Exception:
                log.exception("Failed to mark execution process offline")
            finally:
                self.store.close()


def concurrency_value(value):
    try:
        number = int(value)
    except (TypeError, ValueError) as error:
        raise argparse.ArgumentTypeError("concurrency must be an integer from 1 to 32") from error
    if str(number) != str(value) or not 1 <= number <= 32:
        raise argparse.ArgumentTypeError("concurrency must be an integer from 1 to 32")
    return number


def run_slot(instance_id, slot, concurrency, stopping, store_factory, worker_factory):
    """Spawn entry point: never inherit live database clients or environment state."""
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(processName)s %(levelname)s %(message)s")
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    signal.signal(signal.SIGTERM, lambda *_: stopping.set())
    store = store_factory()
    try:
        # Idempotent indexes are safe to create concurrently in each child.
        store.indexes()
        worker = worker_factory(store, instance_id=instance_id, slot=slot,
                                concurrency=concurrency, stopping=stopping)
    except BaseException:
        store.close()
        raise
    worker.run()  # Worker owns the Store from here, including cleanup.


class WorkerPool:
    """Supervise independent, bounded execution processes in one container."""
    def __init__(self, concurrency=4, store_factory=Store, worker_factory=Worker,
                 *, shutdown_timeout=20):
        self.concurrency = concurrency_value(concurrency)
        self.store_factory = store_factory
        self.worker_factory = worker_factory
        self.instance_id = socket.gethostname() + "-" + uuid4().hex[:8]
        # Spawn on every platform: fork would inherit sockets, threads and parsers.
        self.context = multiprocessing.get_context("spawn")
        self.stopping = self.context.Event()
        self.shutdown_timeout = shutdown_timeout

    def run(self):
        processes = []
        try:
            log.info("Starting benchmark worker %s with %d execution processes",
                     self.instance_id, self.concurrency)
            # A process consumes only when free; excess jobs stay in Redis/Mongo.
            for slot in range(1, self.concurrency + 1):
                if self.stopping.is_set():
                    break
                process = self.context.Process(target=run_slot,
                    name=f"benchmark-{slot}", args=(self.instance_id, slot,
                        self.concurrency, self.stopping, self.store_factory, self.worker_factory))
                process.start()
                processes.append(process)
            while processes and not self.stopping.is_set():
                ready = wait([process.sentinel for process in processes], timeout=0.5)
                if ready:
                    process = next(item for item in processes if item.sentinel in ready)
                    process.join()
                    if not self.stopping.is_set() or process.exitcode != 0:
                        raise RuntimeError(f"Benchmark execution process {process.name} "
                                           f"exited unexpectedly (exit code {process.exitcode})")
        finally:
            self.stopping.set()
            # One shared deadline keeps shutdown within Compose's 30-second grace.
            deadline = time.monotonic() + self.shutdown_timeout
            for process in processes:
                process.join(timeout=max(0, deadline - time.monotonic()))
            remaining = [process for process in processes if process.is_alive()]
            for process in remaining:
                log.warning("Execution process %s did not stop in time; terminating", process.name)
                process.terminate()
            deadline = time.monotonic() + 2
            for process in remaining:
                process.join(timeout=max(0, deadline - time.monotonic()))
            for process in remaining:
                if process.is_alive():
                    process.kill()
            for process in processes:
                process.join()
                process.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", nargs="?", choices=("work", "download", "smoke"), default="work")
    parser.add_argument("--concurrency", type=concurrency_value,
                        default=os.getenv("BENCHMARK_WORKER_CONCURRENCY", "4"),
                        help="parallel tests in this container (1-32, default: 4)")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if args.command == "download":
        download_data()
        return
    if args.command == "smoke":
        env, games = make_environment(CONFIG, "valid_unseen", 2, 42)
        try:
            print({"games": len(games), "observation": env.reset()[0], "look": env.step(["look"])[0]})
        finally:
            env.close()
        return
    worker = WorkerPool(args.concurrency)
    for signum in (signal.SIGTERM, signal.SIGINT):
        signal.signal(signum, lambda *_: worker.stopping.set())
    worker.run()


if __name__ == "__main__":
    main()
