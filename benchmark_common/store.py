"""Mongo owns job state; Redis Streams only carries durable job notifications."""
import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from pymongo import ASCENDING, DESCENDING, MongoClient, ReturnDocument
from redis import Redis
from redis.exceptions import ResponseError

LEASE_SECONDS = 60
GROUP = "benchmark_workers"


def now():
    return datetime.now(timezone.utc)


def public(document):
    if document is None:
        return None
    return {key: value for key, value in document.items() if key != "_id"}


class Store:
    def __init__(self, database=None, queue=None):
        self.mongo = None
        if database is None:
            options = {"host": os.getenv("MONGO_HOST", "mongodb"),
                       "port": int(os.getenv("MONGO_PORT", "27017")),
                       "serverSelectionTimeoutMS": 5000, "connectTimeoutMS": 5000,
                       "socketTimeoutMS": 10000, "tz_aware": True}
            if os.getenv("MONGO_USER"):
                options.update(username=os.environ["MONGO_USER"], password=os.getenv("MONGO_PASS", ""),
                               authSource=os.getenv("MONGO_AUTH_SOURCE", "admin"))
            self.mongo = MongoClient(**options)
            database = self.mongo[os.getenv("MONGO_DATABASE", "agent")]
        self.db = database
        self.redis = queue if queue is not None else Redis(
            host=os.getenv("REDIS_HOST", "redis"), port=int(os.getenv("REDIS_PORT", "6379")),
            db=int(os.getenv("REDIS_DB", "0")), password=os.getenv("REDIS_PASSWORD") or None,
            socket_connect_timeout=5, socket_timeout=5, decode_responses=True)
        self.stream = os.getenv("BENCHMARK_QUEUE", "aagent:benchmark:jobs")
        self.jobs = database.benchmark_jobs
        self.episodes = database.benchmark_episodes
        self.events = database.benchmark_events
        self.workers = database.benchmark_workers

    def indexes(self):
        self.jobs.create_index("job_id", unique=True)
        self.jobs.create_index([("created_at", DESCENDING), ("job_id", DESCENDING)])
        self.jobs.create_index([("status", ASCENDING), ("dispatch_after", ASCENDING)])
        self.jobs.create_index([("status", ASCENDING), ("lease_until", ASCENDING)])
        self.episodes.create_index([("job_id", ASCENDING), ("index", ASCENDING)], unique=True)
        self.events.create_index([("job_id", ASCENDING), ("seq", ASCENDING)], unique=True)
        self.events.create_index([("job_id", ASCENDING), ("episode_index", ASCENDING), ("seq", ASCENDING)])
        self.workers.create_index("worker_id", unique=True)

    def close(self):
        self.redis.close()
        if self.mongo:
            self.mongo.close()

    def create(self, config, workflow_name):
        stamp = now()
        job = {"job_id": uuid4().hex, "schema_version": 1, "status": "queued",
               "config": config, "workflow_name": workflow_name, "created_at": stamp,
               "updated_at": stamp, "dispatch_after": stamp, "event_seq": 0,
               "summary": {"requested": config["episodes"], "completed": 0,
                           "successes": 0, "errors": 0, "success_rate": 0}}
        self.jobs.insert_one(job)
        return public(job)

    def get(self, job_id):
        return public(self.jobs.find_one({"job_id": job_id}))

    def dispatch(self, limit=20):
        # The persisted queued job is an outbox. Retry a lost or failed Redis
        # publish without creating another job; claim() fences duplicates.
        for _ in range(limit):
            stamp = now()
            job = self.jobs.find_one_and_update(
                {"status": "queued", "dispatch_after": {"$lte": stamp}},
                {"$set": {"dispatch_after": stamp + timedelta(seconds=30)}},
                sort=[("created_at", ASCENDING)], return_document=ReturnDocument.AFTER)
            if job is None:
                return
            try:
                self.redis.xadd(self.stream, {"job_id": job["job_id"]}, maxlen=10000, approximate=True)
                self.jobs.update_one({"job_id": job["job_id"], "status": "queued"},
                                     {"$unset": {"dispatch_error": ""}})
            except Exception as error:
                self.jobs.update_one({"job_id": job["job_id"], "status": "queued"},
                                     {"$set": {"dispatch_error": str(error)[:1000]}})
                raise

    def ensure_group(self):
        try:
            self.redis.xgroup_create(self.stream, GROUP, id="0", mkstream=True)
        except ResponseError as error:
            if "BUSYGROUP" not in str(error):
                raise

    def claim(self, job_id, worker_id):
        stamp = now()
        return public(self.jobs.find_one_and_update(
            {"job_id": job_id, "status": "queued"},
            {"$set": {"status": "running", "worker_id": worker_id,
                      "started_at": stamp, "updated_at": stamp,
                      "lease_until": stamp + timedelta(seconds=LEASE_SECONDS)}},
            return_document=ReturnDocument.AFTER))

    def heartbeat(self, worker_id, job_id=None, dataset_ready=False, *,
                  instance_id=None, slot=1, concurrency=1):
        stamp = now()
        self.workers.update_one({"worker_id": worker_id}, {"$set": {
            "last_seen": stamp, "job_id": job_id, "dataset_ready": dataset_ready,
            "instance_id": instance_id or worker_id, "slot": slot, "concurrency": concurrency,
            "pid": os.getpid()},
            "$unset": {"stopped_at": ""}}, upsert=True)
        if job_id:
            result = self.jobs.update_one(
                {"job_id": job_id, "worker_id": worker_id, "status": "running",
                 "lease_until": {"$gt": stamp}},
                {"$set": {"lease_until": stamp + timedelta(seconds=LEASE_SECONDS), "updated_at": stamp}})
            return result.modified_count == 1
        return True

    def offline(self, worker_id):
        self.workers.update_one({"worker_id": worker_id},
                                {"$set": {"stopped_at": now(), "job_id": None}})

    def reap(self):
        stamp = now()
        while True:
            job = self.jobs.find_one_and_update(
                {"status": "running", "lease_until": {"$lte": stamp}},
                {"$set": {"status": "failed", "finished_at": stamp, "updated_at": stamp,
                          "error": "Worker heartbeat expired; partial traces retained. Start a new test to rerun."}},
                return_document=ReturnDocument.AFTER)
            if job is None:
                break
            self.episodes.update_many({"job_id": job["job_id"], "status": "running"},
                                      {"$set": {"status": "interrupted", "finished_at": stamp}})

    def owner_filter(self, job_id, worker_id):
        return {"job_id": job_id, "worker_id": worker_id, "status": "running",
                "lease_until": {"$gt": now()}}

    def update_running(self, job_id, worker_id, fields):
        return self.jobs.update_one(self.owner_filter(job_id, worker_id),
                                   {"$set": dict(fields, updated_at=now())}).matched_count == 1

    def append(self, job_id, worker_id, episode_index, record):
        job = self.jobs.find_one_and_update(self.owner_filter(job_id, worker_id),
                   {"$inc": {"event_seq": 1}}, return_document=ReturnDocument.AFTER)
        if job is None:
            raise RuntimeError("Benchmark job lease lost")
        self.events.insert_one(dict(record, job_id=job_id, episode_index=episode_index,
                                    seq=job["event_seq"], created_at=now()))

    def maintenance(self):
        self.reap()
        self.dispatch()
