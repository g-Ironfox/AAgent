"""HTTP-only bridge to the existing AAgent terminal API."""

import json
import time

import requests


class ProtocolError(RuntimeError):
    pass


class TerminalClient:
    def __init__(self, base_url, request_timeout=15, poll_interval=0.5, check=None):
        self.base_url = base_url.rstrip("/")
        self.request_timeout = request_timeout
        self.poll_interval = poll_interval
        self.session = requests.Session()
        self.cursor = None
        self.check = check or (lambda: None)

    def close(self):
        self.session.close()

    def request(self, method, path, **kwargs):
        # POST is never automatically retried: a lost response may follow a
        # successful enqueue, and retrying could advance the environment twice.
        response = self.session.request(
            method, self.base_url + path, timeout=self.request_timeout, **kwargs
        )
        if not response.ok:
            raise RuntimeError(f"{method} {path}: HTTP {response.status_code}: {response.text[:1000]}")
        return response.json()

    def start(self, workflow_file_id, terminal_id, inputs, timeout):
        self.cursor = None
        self.request("POST", "/api/processes", json={
            "workflow_file_id": workflow_file_id, "terminal_id": terminal_id, "inputs": inputs,
        })
        # Creation is asynchronous. Sending input before the terminal is indexed
        # would save history but lose that input from the Workflow's queue.
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.check()
            sessions = self.request("GET", "/api/terminal/sessions")["sessions"]
            record = next((item for item in sessions if item["terminal_id"] == terminal_id), None)
            if record is not None:
                if record["status"] == "closed":
                    raise RuntimeError(f"Workflow closed during startup: {record.get('workflow_status')}")
                return
            time.sleep(self.poll_interval)
        raise TimeoutError(f"Workflow terminal was not created within {timeout}s: {terminal_id}")

    def send(self, terminal_id, message):
        return self.request("POST", "/api/terminal", json={
            "terminal_id": terminal_id,
            "content": json.dumps(message, ensure_ascii=False, allow_nan=False),
        })

    def action(self, terminal_id, episode_id, step, timeout):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.check()
            params = {"terminal_id": terminal_id, "limit": 150}
            if self.cursor is not None:
                params["cursor"] = self.cursor
            page = self.request("GET", "/api/terminal/output", params=params)
            for item in page["items"]:
                self.cursor = item["id"]
                try:
                    action = json.loads(item["content"])
                except (ValueError, TypeError):
                    continue  # Human-readable reasoning is not an action.
                if not isinstance(action, dict) or action.get("type") != "action":
                    continue
                if action.get("episode_id") != episode_id:
                    raise ProtocolError("Action episode_id does not match the current episode")
                action_step = action.get("step")
                if type(action_step) is not int or action_step < 0:
                    raise ProtocolError("Action step must be a non-negative integer")
                if action_step < step:
                    continue  # Duplicate of an already executed action.
                if action_step != step:
                    raise ProtocolError(f"Expected action step {step}, got {action_step}")
                text = action.get("text")
                if not isinstance(text, str) or not text.strip():
                    raise ProtocolError("Action text must be non-empty")
                return text.strip()
            self.cursor = page["next_cursor"]
            if len(page["items"]) == 150:
                continue
            time.sleep(self.poll_interval)
        raise TimeoutError(f"No action for episode {episode_id}, step {step} within {timeout}s")
