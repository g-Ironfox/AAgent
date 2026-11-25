"""Serve the WebUI and forward same-origin API requests to the execution environment."""
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import quote, urlsplit, urlunsplit

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

logger = logging.getLogger("aagent.webui")
STATIC = Path(__file__).parent / "static"
HOP_BY_HOP = {
    b"connection", b"keep-alive", b"proxy-authenticate", b"proxy-authorization",
    b"te", b"trailer", b"transfer-encoding", b"upgrade",
}


def forwarded_headers(headers, *, request=False):
    excluded = set(HOP_BY_HOP)
    for name, value in headers:
        if name.lower() == b"connection":
            excluded.update(token.strip().lower() for token in value.split(b","))
    if request:
        # Let HTTPX generate Host for the configured upstream.
        excluded.add(b"host")
    return [(name, value) for name, value in headers if name.lower() not in excluded]


class RevalidatingStaticFiles(StaticFiles):
    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-store" if path.endswith(".html") else "no-cache"
        return response


def create_app(environment_url=None, transport=None):
    upstream = (environment_url or os.getenv("AGENT_ENVIRONMENT_URL", "http://agent_environment:8080")).rstrip("/")

    @asynccontextmanager
    async def lifespan(app):
        async with httpx.AsyncClient(
            transport=transport, trust_env=False, follow_redirects=False,
            timeout=httpx.Timeout(120, connect=5),
        ) as client:
            app.state.environment_client = client
            yield

    app = FastAPI(title="AAgent WebUI", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

    @app.middleware("http")
    async def security_headers(request, call_next):
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = "default-src 'self'; style-src 'self'; script-src 'self'; connect-src 'self'; img-src 'self' data:"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    @app.get("/healthz")
    def health():
        return {"status": "ok"}

    @app.api_route("/api/{path:path}", methods=["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
    async def proxy(request: Request, path: str):
        # Preserve escaped file IDs and duplicate query parameters. The upstream
        # always comes from deployment configuration, never the incoming URL.
        raw_path = request.scope.get("raw_path") or quote(request.url.path, safe="/").encode("ascii")
        url = upstream.encode("ascii") + raw_path
        if request.scope["query_string"]:
            url += b"?" + request.scope["query_string"]
        client = request.app.state.environment_client
        outgoing = client.build_request(
            request.method, httpx.URL(url.decode("ascii")),
            headers=forwarded_headers(request.headers.raw, request=True),
            content=request.stream(),
        )
        try:
            response = await client.send(outgoing, stream=True)
        except httpx.TimeoutException:
            logger.warning("execution environment request timed out")
            return JSONResponse(status_code=504, content={"error": "agent environment request timed out"})
        except httpx.RequestError:
            logger.warning("execution environment unavailable", exc_info=True)
            return JSONResponse(status_code=502, content={"error": "agent environment unavailable"})

        async def body():
            try:
                # Keep compressed bytes and matching content headers intact.
                async for chunk in response.aiter_raw():
                    yield chunk
            finally:
                await response.aclose()

        result = StreamingResponse(body(), status_code=response.status_code)
        result.raw_headers = forwarded_headers(response.headers.raw)
        location = response.headers.get("location")
        if location:
            target, origin = urlsplit(location), urlsplit(upstream)
            if target.scheme == origin.scheme and target.netloc == origin.netloc:
                # FastAPI's slash redirects must stay on the browser's origin.
                result.headers["location"] = urlunsplit(("", "", target.path, target.query, target.fragment))
        return result

    @app.get("/", include_in_schema=False)
    def home_page():
        return RedirectResponse("/terminal.html", status_code=307)

    def page(filename):
        return FileResponse(STATIC / filename, headers={"Cache-Control": "no-store"})

    @app.get("/workspace", include_in_schema=False)
    def workspace_page():
        return page("workspace.html")

    @app.get("/workspace/replay", include_in_schema=False)
    def replay_page():
        return page("replay.html")

    @app.get("/logs", include_in_schema=False)
    def logs_page():
        return page("workflow-logs.html")

    @app.get("/scheduler", include_in_schema=False)
    def scheduler_page():
        return page("scheduler.html")

    @app.get("/workspace.html", include_in_schema=False)
    @app.get("/document.html", include_in_schema=False)
    def legacy_workspace_page():
        return RedirectResponse("/workspace", status_code=308)

    app.mount("/", RevalidatingStaticFiles(directory=STATIC, html=True), name="static")
    return app


app = create_app()
