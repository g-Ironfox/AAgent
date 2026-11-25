"""Exercise the ALFWorld three-workflow bundle with real scheduling and file ACLs."""
import copy
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
from build_alfworld_bundle import build_bundle, DESTINATION, INITIAL_EXPERIENCE, _deployment_bindings
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
        # Exercise real time-sliced scheduling without serializing the large
        # bootstrap after every individual node (scheduler tests cover that).
        slice_patcher = patch("main.SCHEDULER_TIME_SLICE_MS", 50)
        slice_patcher.start()
        self.addCleanup(slice_patcher.stop)

    def start(self, terminal="alfworld-test"):
        file = self.store.get_file(self.by_role["bootstrap"]["file_id"])
        process = build_workflow_process(json.loads(file["content"]), {}, file["file_id"], file["name"],
                                         terminal, file["permissions"])
        return main.create_process(process).to_record()

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
                # Local examples may have explicitly bound model/file IDs;
                # those values can differ, but their graph must still match.
                document = json.loads(content)
                expected = copy.deepcopy(item["content"])
                bindings = _deployment_bindings(document)
                for node in expected["nodes"]:
                    if node["id"] in bindings:
                        if node["type"] == "llm":
                            node["arguments"]["model"] = bindings[node["id"]]
                        else:
                            node["arguments"]["append_items"] = [{"type": "fixed", "value": bindings[node["id"]]}]
                self.assertEqual(document, expected)
                experiment = DESTINATION.parents[2] / "experiments/alfworld-recovery-scope/workflows" / item["name"]
                experiment_workflow = json.loads(experiment.read_text(encoding="utf-8"))
                validate_workflow(experiment_workflow)
                parse_workflow(experiment_workflow)
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
            self.assertEqual(len(progress["events"]), 4)
            final_observation, _ = self.observe(root, 2, done=True, success=True, reason="success")
        saved, record = self.record(root)
        self.assertEqual(saved["result"]["status"], "completed")
        task = record
        self.assertEqual(json.loads(task["result"]), final_observation)
        events = task["events"]
        self.assertEqual(len(events), 5)
        self.assertEqual(json.loads(events[-1]["observation"]), final_observation)
        self.assertEqual([json.loads(e["observation"])["step"] for e in events if e["type"] == "observation"], [0, 1, 2])
        self.assertEqual([e["reasoning"] for e in events if e["type"] == "turn"], ["search first", "wash it"])
        self.assertNotIn("task_record", record)
        self.assertTrue(all(isinstance(e, dict) for e in events))
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
        observation = json.loads(record["result"])
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
        task = record
        events = task["events"]
        attempts = events[1]["attempts"]
        self.assertTrue(all("result" not in a for a in attempts))
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
        task = record
        event = task["events"][1]
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

    def test_long_episode_records_deltas_once_and_stays_under_file_limit(self):
        turns = 12
        reasoning = [('reasoning-%02d: "quoted" C:\\room\\pillow\n' % i) + ('x' * 6000) for i in range(turns)]
        llm = Mock(side_effect=[*(('look', item, []) for item in reasoning), ('# learned', '', [])])
        with patch.dict(sys.modules, {"llm": SimpleNamespace(chat_with_model=llm)}):
            root = self.start()
            self.drain()
            for step in range(turns):
                self.observe(root, step)
            self.observe(root, turns, done=True, success=True, reason="success")
        saved, record = self.record(root)
        events = record["events"]
        self.assertEqual(len(events), turns * 2 + 1)
        self.assertEqual([e["reasoning"] for e in events if e["type"] == "turn"], reasoning)
        self.assertTrue(all("history" not in e and "outcome" not in e for e in events))
        # Read the actual file payload, including workspace metadata, not a size estimate.
        content = self.store.get_file(saved["result"]["record_file_id"])["content"]
        self.assertLess(len(content), 150_000)
        self.assertNotIn("workspace_changes", record)
        for step in range(turns):
            self.assertEqual(content.count('reasoning-%02d:' % step), 1)
        # Every intermediate write is subject to the real FileRequest 1M-character check.
        self.assertEqual(record["iterator_status"], "completed")
        self.assertEqual(len(llm.call_args_list[turns - 1].args[0]), 2 * turns)
        review = llm.call_args_list[-1].args[0][1]["content"]
        for step in range(turns):
            self.assertEqual(review.count('reasoning-%02d:' % step), 1)

if __name__ == "__main__":
    unittest.main()
