"""Run the fixed three-workflow bundle against scheduler and file permission APIs."""
import copy
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import main
import process_repository as repository
from process_creation import build_workflow_process
import test_process_workflows as process_support
from workflow_nodes import current_workflow_process
from workflow_parser import parse_workflow
from workflow_validator import validate_workflow
from workflow_recovery import build_file_recovery_plan

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from build_restricted_workflows import build_bundle, build_main, DESTINATION
from install_restricted_workflows import install_bundle
from file_store import FileStore
from files import CheckpointRequest, FileRequest, create_files_router
from test_file_store import FakeCollection, FakeWorkspaceCollection


def call(name, arguments, call_id="call-1"):
    return {"id": call_id, "type": "function", "function": {"name": name, "arguments": json.dumps(arguments)}}


class RestrictedWorkflowTest(unittest.TestCase):
    def setUp(self):
        process_support.ProcessWorkflowTest.setUp(self)
        self.store = FileStore(FakeCollection(), FakeWorkspaceCollection())
        self.router = create_files_router(self.store, self.lookup)
        self.installed = install_bundle(self.admin_api, "test-model")
        self.by_role = self.installed["files"]
        self.executed = []
        self.fail_update = False
        self.tools = Mock(side_effect=self.execute_tool)
        tool_patch = patch.dict(sys.modules, {"tools.tool": SimpleNamespace(
            registered_tools=[], tool_handlers={name: object() for name in (
                "workspace.get_file", "workspace.list_files", "workspace.create_file", "workspace.update_file", "workspace.create_checkpoint",
                "workspace.checkpoint_diff", "workspace.get_file_recovery_plan",
            )}, execute_tool=self.tools,
        )})
        tool_patch.start()
        self.addCleanup(tool_patch.stop)
        reader = patch("workflow_parser._read_workspace_workflow_record_by_name", side_effect=self.read_workflow)
        reader.start()
        self.addCleanup(reader.stop)

    def lookup(self, process_id):
        value = self.redis.hget(repository.PROCESSTABLE, process_id)
        return json.loads(value) if value else None

    def endpoint(self, path, method="GET"):
        return next(route.endpoint for route in self.router.routes
                    if route.path == "/api/files" + path and method in route.methods)

    def unwrap(self, response):
        if not isinstance(response, dict):
            raise RuntimeError(f"HTTP {response.status_code}: {response.body.decode()}")
        return response

    def admin_api(self, method, path, payload=None):
        if method == "GET" and path == "":
            return self.endpoint("")(None)
        if method == "POST" and path == "":
            return self.unwrap(self.endpoint("", "POST")(FileRequest(**payload), None))
        if method == "POST" and path == "/checkpoints":
            return self.endpoint(path, method)(CheckpointRequest(**payload), None)
        raise AssertionError((method, path))

    def identity(self):
        process = current_workflow_process.get()
        return process.process_id + ":" + process._workspace_token

    def execute_tool(self, node_id, name, arguments, preserve_result=False):
        process = current_workflow_process.get()
        self.executed.append((process.workflow_name, name, copy.deepcopy(arguments)))
        identity = self.identity()
        if name == "workspace.list_files":
            response = self.endpoint("")(identity)
        elif name == "workspace.get_file":
            response = self.endpoint("/{file_id}")(arguments["file_id"], identity)
        elif name == "workspace.create_file":
            response = self.endpoint("", "POST")(FileRequest(**arguments), identity)
        elif name == "workspace.update_file":
            if self.fail_update and process.workflow_name.endswith("-iterator.flow"):
                raise RuntimeError("simulated experience revision conflict")
            arguments = dict(arguments)
            file_id = arguments.pop("file_id")
            response = self.endpoint("/{file_id}", "PUT")(file_id, FileRequest(**arguments), identity)
        elif name == "workspace.create_checkpoint":
            response = self.endpoint("/checkpoints", "POST")(CheckpointRequest(**arguments), identity)
        elif name == "workspace.checkpoint_diff":
            response = self.endpoint("/checkpoints/{seq}/diff")(arguments["seq"], identity)
        elif name == "workspace.get_file_recovery_plan":
            return build_file_recovery_plan(**arguments, request=self.recovery_request)
        else:
            raise AssertionError("unexpected tool: " + name)
        return self.unwrap(response)

    def recovery_request(self, method, path):
        self.assertEqual(method, "GET")
        if path.startswith("/checkpoints/"):
            return self.unwrap(self.endpoint("/checkpoints/{seq}/diff")(int(path.split("/")[2]), self.identity()))
        return self.unwrap(self.endpoint("/{file_id}")(path[1:], self.identity()))

    def main_version(self, label, checkpoint=False):
        file = self.store.get_file(self.by_role["main"]["file_id"])
        doc = json.loads(file["content"])
        doc["description"] = label
        self.store.update_file(file["file_id"], file["name"], json.dumps(doc, ensure_ascii=False), file["revision"])
        if checkpoint:
            return self.store.create_checkpoint(label)["seq"]

    def read_workflow(self, name):
        item = next(item for item in self.store.list_files() if item["name"] == name)
        file = self.unwrap(self.endpoint("/{file_id}")(item["file_id"], self.identity()))
        return json.loads(file["content"]), file["permissions"]

    def start(self, task="完成任务，保留引号 \"、换行\n以及中文"):
        file = self.store.get_file(self.by_role["bootstrap"]["file_id"])
        process = build_workflow_process(json.loads(file["content"]), {"task": task}, file["file_id"], file["name"],
                                         "restricted-terminal", file["permissions"])
        return main.create_process(process).to_record()

    def drain(self):
        for _ in range(2000):
            if main.schedule_once(timeout=0.01) is None:
                return
        self.fail("workflow bundle did not quiesce")

    def record(self, root):
        saved = self.lookup(root["process_id"])
        self.assertEqual(saved["status"], "completed", saved.get("error"))
        file = self.store.get_file(saved["result"]["record_file_id"])
        return saved, json.loads(file["content"])

    def test_examples_match_generator_validate_compile_and_use_fixed_targets(self):
        for item in build_bundle():
            content = (DESTINATION / item["name"]).read_text(encoding="utf-8")
            if item["name"].endswith(".flow"):
                self.assertEqual(json.loads(content), item["content"])
                validate_workflow(item["content"])
                parse_workflow(item["content"])
                dynamic = [node["id"] for node in item["content"]["nodes"] if node["type"] == "json_tool"]
                self.assertEqual(dynamic, ["invoke_" + str(i) for i in range(4)]
                                 if item["role"] in ("main", "stable") else [])
            else:
                self.assertEqual(content, item["content"])
        for role in ("experience", "main", "stable", "iterator", "bootstrap"):
            file = self.store.get_file(self.by_role[role]["file_id"])
            self.assertNotIn("REPLACE_WITH_", file["content"])
            self.assertNotIn("UNBOUND_", file["content"])
        self.assertEqual(self.store.get_file(self.by_role["main"]["file_id"])["content"],
                         self.store.get_file(self.by_role["stable"]["file_id"])["content"])

    def test_success_records_task_checkpoints_and_only_iterator_writes_experience(self):
        task = 'write task with "quotes"\nand 中文'
        protected_before = {role: self.store.get_file(self.by_role[role]["file_id"])["content"]
                            for role in ("bootstrap", "iterator", "main", "stable")}
        llm = Mock(side_effect=[("任务完成", "", []), ("# 经验\n已验证的方法。", "", [])])
        with patch.dict(sys.modules, {"llm": SimpleNamespace(chat_with_model=llm)}):
            root = self.start(task)
            self.drain()
        saved, record = self.record(root)
        self.assertEqual(saved["result"]["status"], "completed")
        task_record = json.loads(record["task_record"])
        self.assertEqual(task_record["task"], task)
        self.assertEqual(json.loads(task_record["result"]), {"result": "任务完成"})
        self.assertEqual(record["iterator_status"], "completed")
        self.assertGreater(task_record["checkpoint_after"], task_record["checkpoint_before"])
        for field in ("workspace_before", "workspace_after"):
            inventory = json.loads(task_record[field])
            self.assertIsInstance(inventory["items"], list)
            self.assertTrue(all(isinstance(item, dict) for item in inventory["items"]))
            self.assertIsInstance(inventory["revision"], int)
        changes = json.loads(task_record["workspace_changes"])
        self.assertEqual(changes["seq"], task_record["checkpoint_after"])
        self.assertEqual(changes["parent_seq"], task_record["checkpoint_before"])
        self.assertIsInstance(changes["changes"], list)
        self.assertEqual(self.store.get_file(self.by_role["experience"]["file_id"])["content"], "# 经验\n已验证的方法。")
        updates = [(workflow, args["file_id"]) for workflow, name, args in self.executed if name == "workspace.update_file"]
        iterator_updates = [file_id for workflow, file_id in updates if workflow.endswith("-iterator.flow")]
        self.assertEqual(iterator_updates, [self.by_role["experience"]["file_id"]])
        self.assertFalse(llm.call_args.kwargs["tools"])
        for role, content in protected_before.items():
            self.assertEqual(self.store.get_file(self.by_role[role]["file_id"])["content"], content)
        self.assertEqual(len(self.store.list_checkpoints()), 4)

    def test_invalid_main_is_restored_and_retried_with_task_files_preserved(self):
        main_file = self.store.get_file(self.by_role["main"]["file_id"])
        permissions = copy.deepcopy(main_file["permissions"])
        self.store.update_file(main_file["file_id"], main_file["name"], "{broken", main_file["revision"])
        artifact = self.store.create_file("existing-task.txt", "keep me")
        llm = Mock(side_effect=[("恢复后完成", "", []), ("# 经验\n记录恢复。", "", [])])
        with patch.dict(sys.modules, {"llm": SimpleNamespace(chat_with_model=llm)}):
            root = self.start()
            self.drain()
        saved, record = self.record(root)
        self.assertEqual(saved["result"]["status"], "recovered")
        self.assertTrue(json.loads(record["task_record"])["error"])
        restored = self.store.get_file(main_file["file_id"])
        self.assertEqual(restored["permissions"], permissions)
        self.assertEqual(restored["content"], self.store.get_file(self.by_role["stable"]["file_id"])["content"])
        self.assertEqual(self.store.get_file(artifact["file_id"])["content"], "keep me")

    def test_failure_at_stable_stops_without_repeating_stable(self):
        llm = Mock(side_effect=[RuntimeError("provider down"), ("# 经验\n服务失败。", "", [])])
        with patch.dict(sys.modules, {"llm": SimpleNamespace(chat_with_model=llm)}):
            root = self.start()
            self.drain()
        saved, record = self.record(root)
        self.assertEqual(saved["result"]["status"], "failed")
        details = json.loads(record["task_record"])
        self.assertIn("provider down", details["error"])
        self.assertEqual(len(details["attempts"]), 1)
        self.assertEqual(record["iterator_status"], "completed")
        self.assertFalse(any(name == "workspace.update_file" and args["file_id"] == self.by_role["main"]["file_id"]
                             for _, name, args in self.executed))

    def test_recovery_tries_history_then_stable_and_records_every_attempt(self):
        self.main_version("intermediate", checkpoint=True)
        self.main_version("latest", checkpoint=True)
        self.store.create_checkpoint("same latest content")
        llm = Mock(side_effect=[RuntimeError("latest failed"), RuntimeError("intermediate failed"),
                                ("stable succeeded", "", []), ("history learned", "", [])])
        with patch.dict(sys.modules, {"llm": SimpleNamespace(chat_with_model=llm)}):
            root = self.start()
            self.drain()
        saved, record = self.record(root)
        self.assertEqual(saved["result"]["status"], "recovered")
        details = json.loads(record["task_record"])
        attempts = [json.loads(item) for item in details["attempts"]]
        self.assertEqual([item["source"] for item in attempts], ["current", "checkpoint", "stable"])
        self.assertEqual([item["status"] for item in attempts], ["failed", "failed", "recovered"])
        self.assertIn("latest failed", details["error"])
        self.assertIn("intermediate failed", details["error"])
        restored = [json.loads(args["content"])["description"] for _, name, args in self.executed
                    if name == "workspace.update_file" and args["file_id"] == self.by_role["main"]["file_id"]]
        stable = json.loads(self.store.get_file(self.by_role["stable"]["file_id"])["content"])
        self.assertEqual(restored, ["intermediate", stable["description"]])

    def test_recovery_stops_at_first_successful_older_version(self):
        self.main_version("working older version", checkpoint=True)
        self.main_version("broken latest", checkpoint=True)
        llm = Mock(side_effect=[RuntimeError("latest failed"), ("older succeeded", "", []), ("learned", "", [])])
        with patch.dict(sys.modules, {"llm": SimpleNamespace(chat_with_model=llm)}):
            root = self.start()
            self.drain()
        saved, record = self.record(root)
        self.assertEqual(saved["result"]["status"], "recovered")
        self.assertEqual(len(json.loads(record["task_record"])["attempts"]), 2)
        current = json.loads(self.store.get_file(self.by_role["main"]["file_id"])["content"])
        self.assertEqual(current["description"], "working older version")

    def test_recovery_exhaustion_attempts_stable_once(self):
        self.main_version("intermediate", checkpoint=True)
        self.main_version("latest", checkpoint=True)
        llm = Mock(side_effect=[RuntimeError("latest failed"), RuntimeError("intermediate failed"),
                                RuntimeError("stable failed"), ("failures learned", "", [])])
        with patch.dict(sys.modules, {"llm": SimpleNamespace(chat_with_model=llm)}):
            root = self.start()
            self.drain()
        saved, record = self.record(root)
        self.assertEqual(saved["result"]["status"], "failed")
        attempts = [json.loads(item) for item in json.loads(record["task_record"])["attempts"]]
        self.assertEqual([item["source"] for item in attempts], ["current", "checkpoint", "stable"])
        self.assertEqual(record["iterator_status"], "completed")
        self.assertEqual(llm.call_count, 4)

    def test_fixed_tool_failure_reaches_bootstrap_recovery(self):
        self.main_version("experimental")
        failed = False

        def execute(node_id, name, arguments, preserve_result=False):
            nonlocal failed
            process = current_workflow_process.get()
            if not failed and node_id == "read_experience" and process.workflow_name.endswith("-main.flow"):
                failed = True
                raise RuntimeError("experience temporarily unavailable")
            return self.execute_tool(node_id, name, arguments, preserve_result)

        self.tools.side_effect = execute
        llm = Mock(side_effect=[("恢复后完成任务", "", []), ("保留失败经验", "", [])])
        with patch.dict(sys.modules, {"llm": SimpleNamespace(chat_with_model=llm)}):
            root = self.start()
            self.drain()
        saved, record = self.record(root)
        self.assertTrue(failed)
        self.assertEqual(saved["result"]["status"], "recovered")
        self.assertIn("experience temporarily unavailable", json.loads(record["task_record"])["error"])
        self.assertEqual(record["iterator_status"], "completed")
        self.assertEqual(llm.call_count, 2)

    def test_iterator_failure_is_recorded_without_overwriting_experience_or_losing_task_result(self):
        before = self.store.get_file(self.by_role["experience"]["file_id"])["content"]
        self.fail_update = True
        llm = Mock(side_effect=[("任务成功", "", []), ("new experience", "", [])])
        with patch.dict(sys.modules, {"llm": SimpleNamespace(chat_with_model=llm)}):
            root = self.start()
            self.drain()
        saved, record = self.record(root)
        self.assertEqual(saved["result"]["status"], "completed")
        self.assertEqual(record["iterator_status"], "failed")
        self.assertIn("revision conflict", record["iterator_result"])
        self.assertEqual(self.store.get_file(self.by_role["experience"]["file_id"])["content"], before)

    def test_task_tools_are_dispatched_and_unlisted_tools_are_never_executed(self):
        calls = [call("workspace.create_file", {"name": "answer.txt", "content": "actual output"}),
                 call("workspace.restore_checkpoint", {"seq": 0}, "forbidden")]
        llm = Mock(side_effect=[("", "", calls), ("文件已创建", "", []), ("# 经验\n记录工具结果。", "", [])])
        with patch.dict(sys.modules, {"llm": SimpleNamespace(chat_with_model=llm)}):
            root = self.start()
            self.drain()
        saved, record = self.record(root)
        self.assertEqual(saved["result"]["status"], "completed")
        changes = json.loads(json.loads(record["task_record"])["workspace_changes"])["changes"]
        self.assertTrue(any(change["after_name"] == "answer.txt" and change["after_content"] == "actual output" for change in changes))
        artifact = next(file for file in self.store.list_files() if file["name"] == "answer.txt")
        self.assertEqual(self.store.get_file(artifact["file_id"])["content"], "actual output")
        self.assertFalse(any(name == "workspace.restore_checkpoint" for _, name, _ in self.executed))
        second_messages = llm.call_args_list[1].args[0]
        self.assertTrue(any("outside the fixed" in msg["content"] for msg in second_messages if msg["role"] == "tool"))

    def test_main_cannot_update_its_definition_or_experience(self):
        targets = [self.store.get_file(self.by_role[role]["file_id"]) for role in ("main", "experience")]
        calls = [call("workspace.update_file", {key: file[key] for key in ("file_id", "name", "content", "revision")}, str(i))
                 for i, file in enumerate(targets)]
        llm = Mock(side_effect=[("", "", calls), ("权限不足", "", []), ("经验保持受控", "", [])])
        with patch.dict(sys.modules, {"llm": SimpleNamespace(chat_with_model=llm)}):
            root = self.start()
            self.drain()
        self.record(root)
        messages = llm.call_args_list[1].args[0]
        errors = [msg for msg in messages if msg["role"] == "tool"]
        self.assertEqual(len(errors), 2)
        self.assertTrue(all("403" in msg["content"] for msg in errors))
        self.assertEqual(self.store.get_file(targets[0]["file_id"])["content"], targets[0]["content"])

    def test_tool_budget_forces_a_final_answer_without_tools(self):
        file = self.store.get_file(self.by_role["main"]["file_id"])
        bounded = json.dumps(build_main("test-model", self.by_role["experience"]["file_id"], max_turns=1))
        self.store.update_file(file["file_id"], file["name"], bounded, file["revision"])
        llm = Mock(side_effect=[("", "", [call("workspace.list_files", {})]), ("轮次耗尽，说明未完成项", "", []), ("记录预算", "", [])])
        with patch.dict(sys.modules, {"llm": SimpleNamespace(chat_with_model=llm)}):
            root = self.start()
            self.drain()
        saved, _ = self.record(root)
        self.assertIn("轮次耗尽", saved["result"]["result"])
        self.assertFalse(llm.call_args_list[1].kwargs["tools"])
        self.assertEqual(llm.call_count, 3)

    def test_installer_refuses_existing_files_and_preserves_experience(self):
        before = copy.deepcopy(self.store.list_files())
        with self.assertRaisesRegex(ValueError, "will not be overwritten"):
            install_bundle(self.admin_api, "test-model")
        self.assertEqual(self.store.list_files(), before)
        with self.assertRaises(ValueError):
            install_bundle(self.admin_api, "REPLACE_WITH_MODEL_ID", prefix="another")
        with self.assertRaises(ValueError):
            install_bundle(self.admin_api, "test-model", prefix="../invalid")


if __name__ == "__main__":
    unittest.main()
