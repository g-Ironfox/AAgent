"""Run with the isolated stack documented in README.md."""
import json
import os
import time
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4
from pathlib import Path

ENVIRONMENT = os.getenv("ENVIRONMENT_URL", "http://agent_environment:8080")
WEBUI = os.getenv("WEBUI_URL", "http://webui:8081")


def request(base, path, method="GET", payload=None, headers=None):
    data = None if payload is None else json.dumps(payload).encode()
    options = {"Content-Type": "application/json", **(headers or {})}
    try:
        response = urlopen(Request(base + path, data=data, method=method, headers=options), timeout=20)
    except HTTPError as error:
        response = error
    with response:
        raw = response.read()
        value = json.loads(raw) if response.headers.get_content_type() == "application/json" else raw
        return response.status, value, response.headers


def wait_for(check, seconds=20):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        value = check()
        if value:
            return value
        time.sleep(0.1)
    raise AssertionError("timed out waiting for runtime state")


@unittest.skipUnless(os.getenv("ENVIRONMENT_INTEGRATION") == "1", "requires isolated acceptance stack")
class EnvironmentIntegrationTest(unittest.TestCase):
    def test_workspace_checkpoint_restore_and_revision_conflicts(self):
        name = "acceptance-" + uuid4().hex
        status, file, _ = request(ENVIRONMENT, "/api/files", "POST", {"name": name, "content": "before"})
        self.assertEqual(status, 201)
        path = "/api/files/" + file["file_id"]
        status, checkpoint, _ = request(ENVIRONMENT, "/api/files/checkpoints", "POST", {"name": name})
        self.assertEqual(status, 201)
        status, updated, _ = request(ENVIRONMENT, path, "PUT", {"name": name, "content": "after", "revision": file["revision"]})
        self.assertEqual(status, 200)
        self.assertEqual(request(ENVIRONMENT, path, "PUT", {"name": name, "content": "stale", "revision": file["revision"]})[0], 409)
        seq = checkpoint["seq"]
        self.assertEqual(request(ENVIRONMENT, f"/api/files/checkpoints/{seq}/restore", "POST")[0], 200)
        status, restored, _ = request(ENVIRONMENT, path)
        self.assertEqual(restored["content"], "before")
        self.assertGreater(restored["revision"], updated["revision"])
        self.assertEqual(request(ENVIRONMENT, "/api/files/checkpoints/tree")[0], 200)
        self.assertEqual(request(ENVIRONMENT, path, headers={"X-AAgent-Process-ID": "unknown:invalid"})[0], 403)
        self.assertEqual(request(ENVIRONMENT, path + "?revision=" + str(restored["revision"]), "DELETE")[0], 200)

    def test_runtime_can_load_workspace_and_exchange_terminal_messages(self):
        suffix = uuid4().hex
        examples = Path(os.getenv("EXAMPLES_DIR", "/examples"))
        child_name = "child-" + suffix + ".flow"
        child = json.loads((examples / "workflow-subprocess-child.flow").read_text(encoding="utf-8"))
        status, _, _ = request(ENVIRONMENT, "/api/files", "POST", {"name": child_name, "content": json.dumps(child)})
        self.assertEqual(status, 201)
        parent = (examples / "workflow-subprocess-terminal.flow").read_text(encoding="utf-8").replace("workflow-subprocess-child.flow", child_name)
        status, root, _ = request(ENVIRONMENT, "/api/files", "POST", {"name": "parent-" + suffix + ".flow", "content": parent})
        self.assertEqual(status, 201)
        terminal = "terminal-" + suffix
        self.assertEqual(request(ENVIRONMENT, "/api/processes", "POST", {"workflow_file_id": root["file_id"], "terminal_id": terminal})[0], 202)
        wait_for(lambda: any(item.get("terminal_id") == terminal for item in request(ENVIRONMENT, "/api/terminal/sessions")[1]["sessions"]))
        self.assertEqual(request(ENVIRONMENT, "/api/terminal", "POST", {"terminal_id": terminal, "content": json.dumps({"name": "hello-" + suffix})})[0], 201)
        output = wait_for(lambda: any("hello-" + suffix in item.get("content", "") for item in request(ENVIRONMENT, "/api/terminal/output?terminal_id=" + terminal)[1].get("items", [])))
        self.assertTrue(output)
        self.assertEqual(request(ENVIRONMENT, "/api/scheduler")[0], 200)

    @unittest.skipIf(os.getenv("WEBUI_OFFLINE") == "1", "frontend intentionally stopped")
    def test_webui_pages_proxy_and_business_errors(self):
        self.assertEqual(request(WEBUI, "/healthz")[0], 200)
        self.assertEqual(request(WEBUI, "/api/health")[0], 200)
        self.assertEqual(request(WEBUI, "/api/files/")[0], 200)
        for path in ["/workspace", "/workspace/replay", "/logs", "/scheduler", "/terminal.html"]:
            status, body, headers = request(WEBUI, path)
            self.assertEqual(status, 200)
            self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertEqual(request(WEBUI, "/api/files/missing-file")[0], 404)
        self.assertEqual(request(WEBUI, "/api/files", headers={"X-AAgent-Process-ID": "unknown:invalid"})[0], 403)
        self.assertEqual(request(WEBUI, "/api/files")[1], request(ENVIRONMENT, "/api/files")[1])


if __name__ == "__main__":
    unittest.main()
