"""Benchmark control plane. Never reads the runtime's private Redis database."""
import logging
import os
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

import requests
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pymongo.errors import PyMongoError
from redis.exceptions import RedisError

from benchmark_common.models import JobConfig
from benchmark_common.store import Store, now, public

log = logging.getLogger("benchmark_webui")
STATIC = Path(__file__).with_name("static")


def create_app(store=None, upstream=None):
    def workflows():
        try:
            if upstream:
                return upstream()
            response = requests.get(os.getenv("AAGENT_API_URL", "http://agent_environment:8080").rstrip("/")
                                    + "/api/processes/workflow-options", timeout=10)
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError) as error:
            log.warning("Workflow options unavailable: %s", error)
            raise HTTPException(503, "Cannot load Workflows from agent_environment") from error

    @asynccontextmanager
    async def lifespan(app):
        backend = store if store is not None else Store()
        backend.indexes()
        app.state.store = backend
        stopped = threading.Event()

        def maintain():
            while not stopped.is_set():
                try:
                    backend.maintenance()
                except Exception:
                    log.exception("Benchmark queue maintenance failed; will retry")
                stopped.wait(5)

        thread = threading.Thread(target=maintain, daemon=True)
        thread.start()
        try:
            yield
        finally:
            stopped.set()
            thread.join(timeout=15)
            if store is None:
                backend.close()

    app = FastAPI(title="AAgent Benchmark", lifespan=lifespan)
    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    def db(request):
        return request.app.state.store

    def require_job(backend, job_id):
        job = backend.get(job_id)
        if job is None:
            raise HTTPException(404, "Benchmark job not found")
        return job

    @app.exception_handler(PyMongoError)
    @app.exception_handler(RedisError)
    async def storage_error(request, error):
        log.error("Benchmark storage unavailable", exc_info=error)
        return JSONResponse(status_code=503, content={"detail": "Benchmark storage unavailable; try again shortly"})

    @app.get("/")
    def index():
        return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-cache"})

    @app.get("/api/health")
    def health(request: Request):
        backend = db(request)
        backend.db.command("ping")
        backend.redis.ping()
        return {"status": "ok"}

    @app.get("/api/options")
    def options(request: Request):
        backend = db(request)
        workers = [public(item) for item in backend.workers.find({}, {"_id": 0}).sort("last_seen", -1).limit(50)]
        for worker in workers:
            worker["online"] = not worker.get("stopped_at") and (now() - worker["last_seen"]).total_seconds() < 30
        return {"workflows": workflows().get("items", []), "workers": workers}

    @app.post("/api/jobs", status_code=202)
    def publish(config: JobConfig, request: Request):
        choices = workflows().get("items", [])
        choice = next((item for item in choices if item["file_id"] == config.workflow_file_id), None)
        if choice is None:
            raise HTTPException(400, "Select an existing Workflow file")
        backend = db(request)
        job = backend.create(config.model_dump(), choice.get("workflow_name") or choice.get("name"))
        try:
            backend.dispatch()
        except Exception:
            # Accepted means persisted. Mongo's outbox will retry Redis delivery.
            log.exception("Job %s saved; Redis dispatch will be retried", job["job_id"])
        return backend.get(job["job_id"])

    @app.get("/api/jobs")
    def list_jobs(request: Request, limit: int = Query(30, ge=1, le=100),
                  before: str | None = None,
                  status: Literal["queued", "running", "completed", "failed"] | None = None):
        backend = db(request)
        query = {"status": status} if status else {}
        if before:
            anchor = require_job(backend, before)
            query["$or"] = [{"created_at": {"$lt": anchor["created_at"]}},
                {"created_at": anchor["created_at"], "job_id": {"$lt": before}}]
        items = [public(item) for item in backend.jobs.find(query, {"metadata": 0}).sort(
            [("created_at", -1), ("job_id", -1)]).limit(limit)]
        return {"items": items, "next_cursor": items[-1]["job_id"] if len(items) == limit else None}

    @app.get("/api/jobs/{job_id}")
    def detail(job_id: str, request: Request):
        return require_job(db(request), job_id)

    @app.get("/api/jobs/{job_id}/episodes")
    def episodes(job_id: str, request: Request, after: int = Query(-1, ge=-1),
                 limit: int = Query(100, ge=1, le=200)):
        backend = db(request)
        require_job(backend, job_id)
        items = [public(item) for item in backend.episodes.find(
            {"job_id": job_id, "index": {"$gt": after}}).sort("index", 1).limit(limit)]
        return {"items": items, "next_cursor": items[-1]["index"] if len(items) == limit else None}

    @app.get("/api/jobs/{job_id}/events")
    def events(job_id: str, request: Request, after: int = Query(0, ge=0),
               episode: int | None = Query(None, ge=0), limit: int = Query(100, ge=1, le=300)):
        backend = db(request)
        require_job(backend, job_id)
        query = {"job_id": job_id, "seq": {"$gt": after}}
        if episode is not None:
            query["episode_index"] = episode
        items = [public(item) for item in backend.events.find(query).sort("seq", 1).limit(limit)]
        return {"items": items, "next_cursor": items[-1]["seq"] if items else after,
                "has_more": len(items) == limit}

    return app


app = create_app()
