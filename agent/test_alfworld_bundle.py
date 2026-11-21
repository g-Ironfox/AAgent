"""Exercise the ALFWorld three-workflow bundle with real scheduling and file ACLs."""
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import main
from process_creation import build_workflow_process
import test_restricted_workflows as support
from workflow_parser import parse_workflow
from workflow_validator import validate_workflow

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from build_alfworld_bundle import build_bundle, DESTINATION, INITIAL_EXPERIENCE
from install_alfworld_workflows import install_bundle


class AlfworldBundleTest(unittest.TestCase):
    # Reuse the workspace API/permission harness, without inheriting its tests.
    lookup = support.RestrictedWorkflowTest.lookup
    endpoint = support.RestrictedWorkflowTest.endpoint
    unwrap = support.RestrictedWorkflowTest.unwrap
    admin_api = support.RestrictedWorkflowTest.admin_api
    identity = support.RestrictedWorkflowTest.identity
    execute_tool = support.RestrictedWorkflowTest.execute_tool
    recovery_request = support.RestrictedWorkflowTest.recovery_request
    main_version = support.RestrictedWorkflowTest.main_version
    read_workflow = support.RestrictedWorkflowTest.read_workflow
    drain = support.RestrictedWorkflowTest.drain
    record = support.RestrictedWorkflowTest.record
    send = support.process_support.ProcessWorkflowTest.send

    def setUp(self):
        with patch.object(support, "install_bundle", install_bundle):
            support.RestrictedWorkflowTest.setUp(self)

    def start(self, terminal="alfworld-test"):
        file = self.store.get_file(self.by_role["bootstrap"]["file_id"])
        process = build_workflow_process(json.loads(file["content"]), {}, file["file_id"], file["name"],
                                         terminal, file["permissions"])
        return main.create_process(process)

    def observe(self, root, step, *, done=False, success=False, reason=None):
        observation = {"type": "observation", "episode_id": root["terminal_id"], "step": step,
            "text": 'task "clean apple"\nroom observation ' + str(step), "done": done, "success": success,
            "score": float(success), "truncated": reason == "max_steps", "reason": reason}
        self.send(root, json.dumps(observation, ensure_ascii=False))
        self.drain()
        saved = self.lookup(root["process_id"])
        self.assertNotEqual(saved["status"], "failed", saved.get("error"))
        return observation, saved

    def actions(self):
        messages = []
        for call in self.output.call_args_list:
            try:
                message = json.loads(call.args[0])
            except ValueError:
                continue
            if message.get("type") in ("action", "error"):
                messages.append(message)
        return messages

    def test_examples_compile_and_install_with_bound_permissions_and_fixed_tools(self):
        for item in build_bundle():
            content = (DESTINATION / item["name"]).read_text(encoding="utf-8")
            if item["name"].endswith(".flow"):
                self.assertEqual(json.loads(content), item["content"])
                validate_workflow(item["content"])
                parse_workflow(item["content"])
                self.assertFalse(any(n["type"] == "json_tool" for n in item["content"]["nodes"]))
                if item["role"] != "bootstrap":
                    self.assertFalse(any(n["type"] in ("read_terminal_queue", "output_to_terminal") for n in item["content"]["nodes"]))
            else:
                self.assertEqual(content, item["content"])
            installed = self.store.get_file(self.by_role[item["role"]]["file_id"])
            self.assertEqual(installed["permissions"], item["permissions"])
            self.assertNotIn("REPLACE_WITH_", installed["content"])
            self.assertNotIn("UNBOUND_", installed["content"])
        self.assertEqual(self.store.get_file(self.by_role["main"]["file_id"])["content"],
                         self.store.get_file(self.by_role["stable"]["file_id"])["content"])
        with self.assertRaisesRegex(ValueError, "will not be overwritten"):
            install_bundle(self.admin_api, "test-model")

    def test_terminal_roundtrip_retains_reasoning_records_real_outcome_and_learns(self):
        llm = Mock(side_effect=[("look", "search first", []), ("clean apple 1 with sinkbasin 1", "wash it", []),
                                ("# ALFWorld experience\nUse sinkbasin to clean.", "", [])])
        writes_before = {role: self.store.get_file(self.by_role[role]["file_id"])["content"]
                         for role in ("main", "stable", "bootstrap", "iterator")}
        with patch.dict(sys.modules, {"llm": SimpleNamespace(chat_with_model=llm)}):
            root = self.start()
            self.drain()
            self.assertEqual(self.lookup(root["process_id"])["status"], "blocked")
            llm.assert_not_called()
            self.observe(root, 0)
            self.assertEqual(self.lookup(root["process_id"])["status"], "blocked")
            self.observe(root, 1)
            # Result/attempt history is already durable while awaiting the next observation.
            progress = next(f for f in self.store.list_files() if "-run-" in f["name"])
            progress = json.loads(self.store.get_file(progress["file_id"])["content"])
            self.assertEqual(len(progress["attempts"]), 4)
            final_observation, _ = self.observe(root, 2, done=True, success=True, reason="success")
        saved, record = self.record(root)
        self.assertEqual(saved["result"]["status"], "completed")
        task = json.loads(record["task_record"])
        self.assertEqual(json.loads(task["result"]), final_observation)
        events = [json.loads(e) for e in task["attempts"]]
        self.assertEqual(len(events), 5)
        self.assertEqual(events[-1], final_observation)
        self.assertEqual([e["step"] for e in events if e.get("type") == "observation"], [0, 1, 2])
        history = llm.call_args_list[1].args[0]
        self.assertEqual([m["role"] for m in history], ["system", "user", "assistant", "user"])
        self.assertEqual(history[2]["reasoning_content"], "search first")
        self.assertIn(INITIAL_EXPERIENCE, history[0]["content"])
        review_record = json.loads(llm.call_args_list[2].args[0][1]["content"].split("本轮记录（JSON）：\n", 1)[1])
        self.assertEqual(json.loads(review_record["result"]), final_observation)
        self.assertEqual(record["iterator_status"], "completed")
        self.assertEqual([a["text"] for a in self.actions()], ["look", "clean apple 1 with sinkbasin 1"])
        self.assertEqual([a["step"] for a in self.actions()], [0, 1])
        for call in self.output.call_args_list:
            self.assertEqual(call.kwargs["terminal_id"], root["terminal_id"])
        for role, content in writes_before.items():
            self.assertEqual(self.store.get_file(self.by_role[role]["file_id"])["content"], content)
        writes = [(name, args["file_id"]) for name, tool, args in self.executed if tool == "workspace.update_file"]
        self.assertTrue(any(name.endswith("-iterator.flow") and target == self.by_role["experience"]["file_id"] for name, target in writes))
        self.assertFalse(any(name.endswith("-main.flow") for name, _ in writes))

    def test_normal_unsolved_episode_does_not_rollback(self):
        llm = Mock(side_effect=[("look", "", []), ("# no new verified success", "", [])])
        with patch.dict(sys.modules, {"llm": SimpleNamespace(chat_with_model=llm)}):
            root = self.start()
            self.drain()
            self.observe(root, 0)
            self.observe(root, 1, done=True, reason="max_steps")
        saved, record = self.record(root)
        self.assertEqual(saved["result"]["status"], "completed")
        observation = json.loads(json.loads(record["task_record"])["result"])
        self.assertFalse(observation["success"])
        self.assertEqual(observation["reason"], "max_steps")
        self.assertFalse(any(tool == "workspace.get_file_recovery_plan" for _, tool, _ in self.executed))
        self.assertEqual(llm.call_count, 2)

    def test_errors_rollback_each_version_then_continue_same_episode_at_stable(self):
        self.main_version("previous version", checkpoint=True)
        self.main_version("broken current")
        llm = Mock(side_effect=[RuntimeError("broken current"), RuntimeError("broken previous"),
            ("look", "same observation after recovery", []), ("inventory", "continue", []), ("# learned recovery", "", [])])
        with patch.dict(sys.modules, {"llm": SimpleNamespace(chat_with_model=llm)}):
            root = self.start()
            self.drain()
            self.observe(root, 0)
            self.assertEqual(len(self.actions()), 1)
            self.observe(root, 1)
            self.observe(root, 2, done=True, reason="max_steps")
        saved, record = self.record(root)
        self.assertEqual(saved["result"]["status"], "recovered")
        task = json.loads(record["task_record"])
        events = [json.loads(e) for e in task["attempts"]]
        attempts = [json.loads(a) for a in events[1]["attempts"]]
        self.assertEqual([a["source"] for a in attempts], ["current", "checkpoint", "stable"])
        self.assertEqual([a["status"] for a in attempts], ["failed", "failed", "recovered"])
        self.assertEqual(llm.call_args_list[0].args[0], llm.call_args_list[1].args[0])
        self.assertEqual(llm.call_args_list[1].args[0], llm.call_args_list[2].args[0])
        self.assertEqual([a["step"] for a in self.actions()], [0, 1])
        self.assertIn("broken current", task["error"])
        self.assertEqual(self.store.get_file(self.by_role["main"]["file_id"])["content"],
                         self.store.get_file(self.by_role["stable"]["file_id"])["content"])

    def test_stable_failure_stops_and_reports_error_without_duplicate_attempt(self):
        llm = Mock(side_effect=[RuntimeError("provider failed at stable"), ("# failure evidence only", "", [])])
        with patch.dict(sys.modules, {"llm": SimpleNamespace(chat_with_model=llm)}):
            root = self.start()
            self.drain()
            self.observe(root, 0)
        saved, record = self.record(root)
        self.assertEqual(saved["result"]["status"], "failed")
        self.assertEqual(llm.call_count, 2)
        self.assertEqual([a["type"] for a in self.actions()], ["error"])
        self.assertIn("provider failed at stable", self.actions()[0]["error"])
        task = json.loads(record["task_record"])
        event = json.loads(task["attempts"][1])
        self.assertEqual(len(event["attempts"]), 1)
        self.assertEqual(record["iterator_status"], "completed")

    def test_iterator_failure_preserves_environment_result_and_experience(self):
        llm = Mock(side_effect=[("look", "", []), RuntimeError("review failed")])
        with patch.dict(sys.modules, {"llm": SimpleNamespace(chat_with_model=llm)}):
            root = self.start()
            self.drain()
            self.observe(root, 0)
            self.observe(root, 1, done=True, success=True, reason="success")
        saved, record = self.record(root)
        self.assertEqual(record["iterator_status"], "failed")
        self.assertTrue(json.loads(saved["result"]["result"])["success"])
        self.assertEqual(self.store.get_file(self.by_role["experience"]["file_id"])["content"], INITIAL_EXPERIENCE)


if __name__ == "__main__":
    unittest.main()
