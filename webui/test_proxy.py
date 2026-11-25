"""Contract checks for page compatibility and the streaming environment proxy."""
import gzip
import unittest
from contextlib import asynccontextmanager

import httpx

from main import create_app


class Chunks(httpx.AsyncByteStream):
    def __init__(self, *chunks):
        self.chunks = chunks
        self.closed = False

    async def __aiter__(self):
        for chunk in self.chunks:
            yield chunk

    async def aclose(self):
        self.closed = True


class WebuiTest(unittest.IsolatedAsyncioTestCase):
    @asynccontextmanager
    async def client(self, handler):
        app = create_app("http://environment.test:8080", transport=httpx.MockTransport(handler))
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://webui.test") as client:
                yield client

    async def test_proxy_preserves_identity_escaped_path_query_and_error(self):
        seen = []
        stream = Chunks(b'{"error":', b'"conflict"}')

        async def upstream(request):
            seen.append(request)
            self.assertEqual(await request.aread(), b'{"revision":7}')
            return httpx.Response(409, headers={"content-type": "application/json", "x-revision": "8"}, stream=stream)

        async with self.client(upstream) as client:
            response = await client.put("/api/files/a%2Fb%E4%B8%AD%E6%96%87?tag=x&tag=y", content=b'{"revision":7}', headers={
                "X-AAgent-Process-ID": "process:token", "Authorization": "Bearer service",
                "Content-Type": "application/json", "Connection": "X-Private", "X-Private": "remove",
            })
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json(), {"error": "conflict"})
        self.assertEqual(response.headers["x-revision"], "8")
        self.assertTrue(stream.closed)
        request = seen[0]
        self.assertEqual(request.url.raw_path, b"/api/files/a%2Fb%E4%B8%AD%E6%96%87?tag=x&tag=y")
        self.assertEqual(request.headers["host"], "environment.test:8080")
        self.assertEqual(request.headers["x-aagent-process-id"], "process:token")
        self.assertEqual(request.headers["authorization"], "Bearer service")
        self.assertNotIn("x-private", request.headers)

    async def test_raw_compression_duplicate_cookies_and_hop_headers(self):
        data = gzip.compress(b'{"items":[]}')
        stream = Chunks(data[:5], data[5:])

        async def upstream(request):
            return httpx.Response(200, stream=stream, headers=[
                ("Content-Type", "application/json"), ("Content-Encoding", "gzip"),
                ("Content-Length", str(len(data))), ("Set-Cookie", "a=1"), ("Set-Cookie", "b=2"),
                ("Connection", "X-Internal"), ("X-Internal", "remove"),
            ])

        async with self.client(upstream) as client:
            response = await client.get("/api/files")
        self.assertEqual(response.json(), {"items": []})
        self.assertEqual(response.headers["content-length"], str(len(data)))
        self.assertEqual(response.headers.get_list("set-cookie"), ["a=1", "b=2"])
        self.assertNotIn("x-internal", response.headers)
        self.assertTrue(stream.closed)

    async def test_redirect_is_forwarded_without_following(self):
        async def upstream(request):
            return httpx.Response(307, headers={"location": "/api/files"}, stream=Chunks())
        async with self.client(upstream) as client:
            response = await client.get("/api/redirect")
        self.assertEqual(response.status_code, 307)
        self.assertEqual(response.headers["location"], "/api/files")

    async def test_absolute_environment_redirect_stays_on_browser_origin(self):
        async def upstream(request):
            return httpx.Response(307, headers={"location": "http://environment.test:8080/api/files?tag=x&tag=y"}, stream=Chunks())
        async with self.client(upstream) as client:
            response = await client.get("/api/files/")
        self.assertEqual(response.status_code, 307)
        self.assertEqual(response.headers["location"], "/api/files?tag=x&tag=y")

    async def test_connection_and_timeout_errors_do_not_retry_commands(self):
        for error, status in [(httpx.ConnectError, 502), (httpx.ReadTimeout, 504)]:
            calls = []
            async def upstream(request):
                calls.append(request)
                raise error("unavailable", request=request)
            async with self.client(upstream) as client:
                response = await client.post("/api/processes", json={})
            self.assertEqual(response.status_code, status)
            self.assertIn("error", response.json())
            self.assertEqual(len(calls), 1)

    async def test_pages_and_local_health_work_without_environment(self):
        async def upstream(request):
            self.fail("static pages and health must not contact environment")
        async with self.client(upstream) as client:
            for path in ["/workspace", "/workspace/replay", "/logs", "/scheduler", "/terminal.html"]:
                response = await client.get(path)
                self.assertEqual(response.status_code, 200, path)
                self.assertEqual(response.headers["cache-control"], "no-store")
                self.assertIn("default-src 'self'", response.headers["content-security-policy"])
            response = await client.get("/api.js")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers["cache-control"], "no-cache")
            self.assertEqual((await client.get("/healthz")).json(), {"status": "ok"})
            for path, status, location in [("/", 307, "/terminal.html"), ("/workspace.html", 308, "/workspace"), ("/document.html", 308, "/workspace")]:
                response = await client.get(path)
                self.assertEqual(response.status_code, status)
                self.assertEqual(response.headers["location"], location)
            self.assertEqual((await client.get("/missing.js")).status_code, 404)

    async def test_large_request_is_streamed_to_backend(self):
        expected = b"x" * (1024 * 1024 + 1)
        async def upstream(request):
            self.assertEqual(await request.aread(), expected)
            return httpx.Response(201, stream=Chunks(b'{"file_id":"created"}'), headers={"Content-Type": "application/json"})
        async with self.client(upstream) as client:
            response = await client.post("/api/files", content=expected)
        self.assertEqual(response.status_code, 201)


if __name__ == "__main__":
    unittest.main()
