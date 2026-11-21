import json
import unittest
from unittest.mock import AsyncMock, patch

from starlette.requests import Request
from starlette.responses import Response


class RequestBodyLimitTest(unittest.IsolatedAsyncioTestCase):
    async def check_limit(self, method, path, size, expected_status, error_message=None):
        # Import the real entrypoint without connecting to MongoDB or Redis.
        with patch("pymongo.MongoClient"), patch("redis.Redis.from_url"), patch("file_store.FileStore"):
            from main import request_body_guard

        request = Request({
            "type": "http", "method": method, "path": path,
            "headers": [(b"content-length", str(size).encode("ascii"))],
        })
        call_next = AsyncMock(return_value=Response(status_code=204))

        result = await request_body_guard(request, call_next)

        self.assertEqual(result.status_code, expected_status)
        if expected_status == 204:
            call_next.assert_awaited_once_with(request)
        else:
            call_next.assert_not_awaited()
            self.assertEqual(json.loads(result.body)["error"], error_message)

    async def test_workspace_file_requests_allow_up_to_128_mib(self):
        limit = 128 * 1024 * 1024
        for method, path in (
            ("POST", "/api/files"),
            ("PUT", "/api/files/example-file"),
            ("POST", "/api/files/checkpoints"),
        ):
            for size, expected_status in (
                (1024 * 1024 + 1, 204),
                (limit - 1, 204),
                (limit, 204),
                (limit + 1, 400),
            ):
                with self.subTest(method=method, path=path, size=size):
                    await self.check_limit(
                        method, path, size, expected_status, "文件请求体不能超过 128 MB",
                    )

    async def test_other_endpoint_limits_are_unchanged(self):
        for path, limit, error_message in (
            ("/api/terminal", 1024 * 1024, "终端请求体不能超过 1 MiB"),
            ("/api/processes", 256 * 1024, "请求体不能超过 256 KB"),
        ):
            for size, expected_status in ((limit, 204), (limit + 1, 400)):
                with self.subTest(path=path, size=size):
                    await self.check_limit("POST", path, size, expected_status, error_message)


if __name__ == "__main__":
    unittest.main()
