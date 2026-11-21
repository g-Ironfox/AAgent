"""Run: python -m unittest discover -s experiments/alfworld-recovery-scope -p 'test_*.py' -v"""
import copy
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "agent"), str(ROOT / "scripts")]
import main
import test_alfworld_bundle as base
import test_restricted_workflows as support
from process_creation import build_workflow_process
from files import FileRequest
from workflow_evolution import prepare_main_update
from workflow_nodes import current_workflow_process
from workflow_parser import parse_workflow
from workflow_validator import validate_workflow
from build_evolving_iterator import build_bundle, SKILL_PATH, DESIGN_NOTES_PATH, upgrade_bundle, install_evolving_bundle
from build_workflow_reference import REFERENCE_PLACEHOLDER, REFERENCE_PERMISSIONS
from install_restricted_workflows import install_files


def improved(document):
    """A genuine graph change, not just a changed description or prompt literal."""
    doc = copy.deepcopy(document)
    doc["nodes"].append({"id": "learned_hint", "type": "construct_content", "dataInputPorts": ["original"],
        "arguments": {"append_items": [{"type": "port", "port_id": "original"},
            {"type": "fixed", "value": "\nLearned test heuristic: inspect receptacles before retrying invalid actions."}]}})
    for e in doc["connections"]:
        if e["fromId"] == "prompt" and e["toId"] == "system":
            e["fromId"] = "learned_hint"
    doc["connections"] += [
        {"fromId": "prompt", "fromPortId": "control-out", "toId": "learned_hint", "toPortId": "control-in", "type": "control"},
        {"fromId": "prompt", "fromPortId": "content-out", "toId": "learned_hint", "toPortId": "original", "type": "content"},
    ]
    return doc


class CandidateTest(unittest.TestCase):
    def setUp(self):
        self.bundle = build_bundle(model="test-model", experience_id="experience-123", main_id="main-123")
        self.document = copy.deepcopy(next(i["content"] for i in self.bundle if i["role"] == "main"))
        self.current = {"name": "test-main.flow", "revision": 7, "content": json.dumps(self.document)}

    def prepare(self, doc, revision=7):
        return prepare_main_update(self.current, revision, json.dumps(doc))

    def test_iterator_compiles_and_reads_reference_without_inlining(self):
        doc = next(i["content"] for i in self.bundle if i["role"] == "iterator")
        validate_workflow(doc)
        parse_workflow(doc)
        context = next(n for n in doc["nodes"] if n["id"] == "evolution_system_text")["arguments"]["append_items"][0]["value"]
        reference = next(i for i in self.bundle if i["role"] == "workflow_reference")
        self.assertIn(SKILL_PATH.read_text(encoding="utf-8"), reference["content"])
        self.assertIn(DESIGN_NOTES_PATH.read_text(encoding="utf-8"), reference["content"])
        self.assertEqual(reference["permissions"], REFERENCE_PERMISSIONS)
        self.assertNotIn(SKILL_PATH.read_text(encoding="utf-8"), context)
        self.assertNotIn("node__llm", json.dumps(doc))
        self.assertTrue(any(c["fromId"] == "evolution_reference" and c["toId"] == "evolution_system_text" for c in doc["connections"]))
        permission = next(i["permissions"] for i in self.bundle if i["role"] == "iterator")
        self.assertEqual(permission["runtime"]["write"], 3)
        self.assertTrue(permission["checkpoints"]["create"])
        self.assertFalse(permission["checkpoints"]["restore"])

    def test_graph_edit_is_ready_and_fenced_json_supported(self):
        doc = improved(self.document)
        self.assertEqual(self.prepare(doc)["status"], "ready")
        result = prepare_main_update(self.current, 7, "```json\n" + json.dumps(doc) + "\n```")
        self.assertEqual(result["status"], "ready")
        self.assertIn("learned_hint", result["content"])
        self.assertEqual(result["revision"], 7)

    def test_noop_and_layout_only_are_unchanged(self):
        self.assertEqual(self.prepare(self.document)["status"], "unchanged")
        self.document["nodes"][0]["x"] = 987
        self.assertEqual(self.prepare(self.document)["status"], "unchanged")

    def test_invalid_json_graph_contract_and_stale_revision_are_rejected(self):
        self.assertEqual(prepare_main_update(self.current, 7, "not json")["status"], "rejected")
        self.assertIn("revision conflict", self.prepare(self.document, 6)["error"])
        for mutate in (
            lambda d: d["connections"].append({"fromId": "unknown", "fromPortId": "control-out", "toId": "out", "toPortId": "control-in", "type": "control"}),
            lambda d: d["input_ports"][0].update(name="other"),
            lambda d: d["nodes"].append({"id": "evil", "type": "invented"}),
        ):
            doc = copy.deepcopy(self.document)
            mutate(doc)
            self.assertEqual(self.prepare(doc)["status"], "rejected")

    def test_model_tools_and_experience_binding_are_protected(self):
        for node_id, key, value in (("react", "model", "another-model"), ("react", "tool_calls", True),
                                   ("read_experience_file_id", "append_items", [{"type": "fixed", "value": "another-file"}])):
            doc = improved(self.document)
            next(n for n in doc["nodes"] if n["id"] == node_id)["arguments"][key] = value
            self.assertEqual(self.prepare(doc)["status"], "rejected", node_id)
        doc = improved(self.document)
        next(n for n in doc["nodes"] if n["id"] == "learned_hint").update(type="output_to_terminal", arguments={})
        self.assertEqual(self.prepare(doc)["status"], "rejected")
        self.current["name"] = "test-stable-main.flow"
        self.assertEqual(self.prepare(improved(self.document))["status"], "rejected")

    def test_local_upgrade_preserves_other_files_and_model_bindings(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            for item in self.bundle:
                content = item["content"]
                (directory / item["name"]).write_text(content if isinstance(content, str) else json.dumps(content), encoding="utf-8")
            (directory / "permissions.json").write_text(json.dumps([{k: v for k, v in i.items() if k != "content"} for i in self.bundle]), encoding="utf-8")
            before = {p.name: p.read_bytes() for p in directory.iterdir()}
            upgrade_bundle(directory, reference_id="uploaded-reference-id")
            upgrade_bundle(directory)  # Re-upgrade must keep the new binding.
            for name in before:
                if name not in {"alfworld-agent-iterator.flow", "permissions.json"}:
                    self.assertEqual((directory / name).read_bytes(), before[name])
            doc = json.loads((directory / "alfworld-agent-iterator.flow").read_text(encoding="utf-8"))
            self.assertEqual({n["arguments"]["model"] for n in doc["nodes"] if n["type"] == "llm"}, {"test-model"})
            validate_workflow(doc)
            binding = next(n for n in doc["nodes"] if n["id"] == "evolution_read_reference_file_id")
            self.assertEqual(binding["arguments"]["append_items"][0]["value"], "uploaded-reference-id")


class EvolutionIntegrationTest(unittest.TestCase):
    # Reuse the existing real scheduler + file API/ACL harness, not its test cases.
    lookup = base.AlfworldBundleTest.lookup
    endpoint = base.AlfworldBundleTest.endpoint
    unwrap = base.AlfworldBundleTest.unwrap
    admin_api = base.AlfworldBundleTest.admin_api
    identity = base.AlfworldBundleTest.identity
    recovery_request = base.AlfworldBundleTest.recovery_request
    main_version = base.AlfworldBundleTest.main_version
    read_workflow = base.AlfworldBundleTest.read_workflow
    drain = base.AlfworldBundleTest.drain
    record = base.AlfworldBundleTest.record
    send = base.AlfworldBundleTest.send
    start = base.AlfworldBundleTest.start
    observe = base.AlfworldBundleTest.observe
    actions = base.AlfworldBundleTest.actions

    def setUp(self):
        installer = install_evolving_bundle
        with patch.object(base, "install_bundle", installer):
            base.AlfworldBundleTest.setUp(self)
        sys.modules["tools.tool"].tool_handlers["workspace.prepare_main_update"] = object()
        self.inject_conflict = False
        self.deny_checkpoint = False

    def execute_tool(self, node_id, name, arguments, preserve_result=False):
        if name == "workspace.prepare_main_update":
            process = current_workflow_process.get()
            self.executed.append((process["workflow_name"], name, copy.deepcopy(arguments)))
            current = self.unwrap(self.endpoint("/{file_id}")(arguments["file_id"], self.identity()))
            return prepare_main_update(current, arguments["revision"], arguments["proposal"])
        if name == "workspace.create_checkpoint" and "before main evolution" in arguments["name"]:
            if self.deny_checkpoint:
                raise RuntimeError("checkpoint unavailable")
            if self.inject_conflict:
                self.main_version("concurrent editor")
        return support.RestrictedWorkflowTest.execute_tool(self, node_id, name, arguments, preserve_result)

    def file(self, role):
        return self.store.get_file(self.by_role[role]["file_id"])

    def episode(self, proposal):
        llm = Mock(side_effect=[("look", "observe", []), (proposal, "", []), ("# updated experience", "", [])])
        with patch.dict(sys.modules, {"llm": SimpleNamespace(chat_with_model=llm)}):
            root = self.start()
            self.drain()
            self.observe(root, 0)
            self.observe(root, 1, done=True, reason="max_steps")
        return root, llm, self.record(root)[1]

    def test_adopts_graph_change_checkpoints_and_next_episode_runs_it(self):
        before = self.file("main")
        stable = self.file("stable")
        iterator = self.file("iterator")
        candidate = improved(json.loads(before["content"]))
        root, llm, record = self.episode(json.dumps(candidate))
        self.assertEqual(record["iterator_status"], "completed")
        detail = json.loads(record["iterator_result"])
        self.assertEqual(detail["main_status"], "updated")
        self.assertGreater(detail["main_after_revision"], detail["main_before_revision"])
        self.assertGreater(detail["main_checkpoint"], 0)
        self.assertEqual(json.loads(self.file("main")["content"]), candidate)
        self.assertEqual(self.file("stable")["content"], stable["content"])
        self.assertEqual(self.file("iterator")["content"], iterator["content"])
        self.assertEqual(self.file("experience")["content"], "# updated experience")
        self.assertIn(self.file("workflow_reference")["content"], llm.call_args_list[1].args[0][0]["content"])
        self.assertIn(SKILL_PATH.read_text(encoding="utf-8"), llm.call_args_list[1].args[0][0]["content"])
        self.assertIn(DESIGN_NOTES_PATH.read_text(encoding="utf-8"), llm.call_args_list[1].args[0][0]["content"])
        self.assertNotIn("Learned test heuristic", str(llm.call_args_list[0]))
        llm2 = Mock(return_value=("look", "next episode", []))
        with patch.dict(sys.modules, {"llm": SimpleNamespace(chat_with_model=llm2)}):
            next_root = self.start("next-episode")
            self.drain()
            self.observe(next_root, 0)
        self.assertIn("Learned test heuristic", str(llm2.call_args_list[0]))
        changes = self.store.checkpoint_diff(detail["main_checkpoint"])
        # Checkpoint precedes the write; historical main has not changed yet.
        self.assertFalse(any(c["file_id"] == before["file_id"] for c in changes["changes"]))

    def test_rejected_candidate_preserves_main_but_still_updates_experience(self):
        before = self.file("main")
        _, _, record = self.episode('{"schema_version":"wrong"}')
        detail = json.loads(record["iterator_result"])
        self.assertEqual(detail["main_status"], "rejected")
        self.assertTrue(detail["main_error"])
        self.assertEqual(detail["main_checkpoint"], 0)
        self.assertEqual(self.file("main")["revision"], before["revision"])
        self.assertEqual(self.file("experience")["content"], "# updated experience")

    def test_unchanged_candidate_never_writes_main_or_checkpoint(self):
        before = self.file("main")
        _, _, record = self.episode(before["content"])
        self.assertEqual(json.loads(record["iterator_result"])["main_status"], "unchanged")
        self.assertEqual(self.file("main")["revision"], before["revision"])
        self.assertFalse(any(t == "workspace.create_checkpoint" and "before main evolution" in a["name"] for _, t, a in self.executed))

    def test_revision_conflict_does_not_overwrite_concurrent_edit(self):
        self.inject_conflict = True
        _, _, record = self.episode(json.dumps(improved(json.loads(self.file("main")["content"]))))
        self.assertEqual(record["iterator_status"], "failed")
        self.assertEqual(json.loads(self.file("main")["content"])["description"], "concurrent editor")
        self.assertNotIn("learned_hint", self.file("main")["content"])

    def test_bad_evolved_main_recovers_to_pre_evolution_version(self):
        before = self.file("main")
        self.episode(json.dumps(improved(json.loads(before["content"]))))
        llm = Mock(side_effect=[RuntimeError("bad evolved logic"), ("look", "recovered", []),
                              (before["content"], "", []), ("# after rollback", "", [])])
        with patch.dict(sys.modules, {"llm": SimpleNamespace(chat_with_model=llm)}):
            root = self.start("rollback-episode")
            self.drain()
            self.observe(root, 0)
            self.observe(root, 1, done=True, reason="max_steps")
        saved, record = self.record(root)
        self.assertEqual(saved["result"]["status"], "recovered")
        self.assertEqual(json.loads(self.file("main")["content"]), json.loads(before["content"]))
        self.assertEqual([a["status"] for a in record["events"][1]["attempts"]], ["failed", "recovered"])
        self.assertEqual(json.loads(record["iterator_result"])["main_status"], "unchanged")

    def test_iterator_acl_cannot_write_stable_bootstrap_or_itself(self):
        file = self.file("iterator")
        process = build_workflow_process(json.loads(file["content"]), {"record": "{}"}, file["file_id"],
                                         file["name"], "acl-probe", file["permissions"])
        root = main.create_process(process)
        token = current_workflow_process.set(root)
        try:
            for role in ("stable", "bootstrap", "iterator", "workflow_reference"):
                target = self.file(role)
                response = self.endpoint("/{file_id}", "PUT")(target["file_id"],
                    FileRequest(name=target["name"], content=target["content"], revision=target["revision"]), self.identity())
                self.assertEqual(response.status_code, 403, role)
                self.assertEqual(self.file(role)["revision"], target["revision"])
        finally:
            current_workflow_process.reset(token)

    def test_reference_is_bound_and_reloaded_each_run(self):
        reference = self.file("workflow_reference")
        iterator = self.file("iterator")
        doc = json.loads(iterator["content"])
        binding = next(n for n in doc["nodes"] if n["id"] == "evolution_read_reference_file_id")
        self.assertEqual(binding["arguments"]["append_items"][0]["value"], reference["file_id"])
        self.assertNotIn(REFERENCE_PLACEHOLDER, iterator["content"])
        sentinel = "\nREFERENCE_RUNTIME_RELOAD_MARKER\n"
        self.store.update_file(reference["file_id"], reference["name"], reference["content"] + sentinel, reference["revision"])
        _, llm, record = self.episode(self.file("main")["content"])
        self.assertEqual(record["iterator_status"], "completed")
        self.assertIn(sentinel, llm.call_args_list[1].args[0][0]["content"])
        self.assertTrue(any(name == "workspace.get_file" and args["file_id"] == reference["file_id"]
                            for _, name, args in self.executed))

    def test_reference_missing_aborts_before_proposal_or_write(self):
        iterator = self.file("iterator")
        doc = json.loads(iterator["content"])
        binding = next(n for n in doc["nodes"] if n["id"] == "evolution_read_reference_file_id")
        binding["arguments"]["append_items"][0]["value"] = "missing-reference"
        self.store.update_file(iterator["file_id"], iterator["name"], json.dumps(doc), iterator["revision"])
        main_before, experience_before = self.file("main"), self.file("experience")
        _, llm, record = self.episode(main_before["content"])
        self.assertEqual(record["iterator_status"], "failed")
        self.assertEqual(llm.call_count, 1)  # Only the main's task decision, no design proposal.
        self.assertEqual(self.file("main")["revision"], main_before["revision"])
        self.assertEqual(self.file("experience")["revision"], experience_before["revision"])
        self.assertFalse(any(name == "workspace.prepare_main_update" for _, name, _ in self.executed))

    def test_reference_can_be_read_at_level_one_but_not_written(self):
        file = self.file("iterator")
        permissions = copy.deepcopy(file["permissions"])
        permissions["runtime"] = {"read": 1, "write": 1}
        process = build_workflow_process(json.loads(file["content"]), {"record": "{}"}, file["file_id"],
                                         file["name"], "read-level-one", permissions)
        root = main.create_process(process)
        token = current_workflow_process.set(root)
        try:
            reference = self.file("workflow_reference")
            response = self.unwrap(self.endpoint("/{file_id}")(reference["file_id"], self.identity()))
            self.assertEqual(response["content"], reference["content"])
            response = self.endpoint("/{file_id}", "PUT")(reference["file_id"],
                FileRequest(name=reference["name"], content="changed", revision=reference["revision"]), self.identity())
            self.assertEqual(response.status_code, 403)
        finally:
            current_workflow_process.reset(token)

    def test_checkpoint_failure_prevents_write(self):
        self.deny_checkpoint = True
        before = self.file("main")
        _, _, record = self.episode(json.dumps(improved(json.loads(before["content"]))))
        self.assertEqual(record["iterator_status"], "failed")
        self.assertEqual(self.file("main")["revision"], before["revision"])


if __name__ == "__main__":
    unittest.main()
