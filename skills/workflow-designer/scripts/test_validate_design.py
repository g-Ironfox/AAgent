"""Integration checks for the standalone skill, exported designs and examples."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from validate_design import DesignError, REPO, export_design, read_json, unique_object, validate_design
from workflow_parser import parse_workflow
from workflow_nodes import propagate_workflow_output, run_workflow_map
from workflow_validator import validate_workflow
from terminal_repository import terminal_process_context

SKILL = Path(__file__).resolve().parents[1] / "SKILL.md"


def load_examples():
    text = SKILL.read_text(encoding="utf-8-sig").split("## 9.", 1)[1]
    return [json.loads(block, object_pairs_hook=unique_object) for block in re.findall(r"```json\s*(.*?)\s*```", text, re.S)]


class WorkflowDesignTest(unittest.TestCase):
    def setUp(self):
        self.examples = load_examples()

    def test_all_embedded_examples_validate_and_compile(self):
        self.assertEqual(len(self.examples), 3)
        for design in self.examples:
            with self.subTest(entrypoint=design["entrypoint"]):
                for item in validate_design(design):
                    self.assertTrue(parse_workflow(item["workflow"]))

    def test_missing_canvas_coordinates_are_rejected(self):
        design = copy.deepcopy(self.examples[0])
        design["workflows"][0]["workflow"]["nodes"][0].pop("x")
        with self.assertRaisesRegex(DesignError, "requires finite numeric x and y"):
            validate_design(design)

    def test_missing_display_name_is_rejected(self):
        design = copy.deepcopy(self.examples[0])
        design["workflows"][0]["workflow"]["nodes"][0].pop("name")
        with self.assertRaisesRegex(DesignError, "requires a nonempty display name"):
            validate_design(design)

    def test_manager_validator_accepts_examples_and_all_agent_envelopes(self):
        script = (
            "import json,sys; from pathlib import Path; "
            "sys.path.insert(0,sys.argv[1]); "
            "from workflow_validator import validate_workflow; "
            "[validate_workflow(i['workflow']) for d in json.load(sys.stdin) for i in d['workflows']]"
        )
        designs = [read_json(REPO / "workflow-design" / name) for name in (
            "initial-agent.design.json", "executor-agent.design.json", "sidecar.design.json")]
        result = subprocess.run([sys.executable, "-c", script, str(REPO / "manager_webui")],
                                input=json.dumps([*self.examples, *designs]), text=True,
                                capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_stale_dependency_snapshot_is_rejected(self):
        design = copy.deepcopy(self.examples[1])
        main = design["workflows"][-1]["workflow"]
        call = next(n for n in main["nodes"] if n["id"] == "process")
        call["output_ports"] = [{"name": "stale", "type": "content"}]
        for edge in main["connections"]:
            if edge["fromId"] == "process" and edge["type"] == "content":
                edge["fromPortId"] = "workflow:stale"
        validate_workflow(main)  # Native static checks alone miss this mismatch.
        with self.assertRaisesRegex(DesignError, "stale output_ports"):
            validate_design(design)

    def test_missing_dependency_is_rejected(self):
        design = copy.deepcopy(self.examples[1])
        design["workflows"].pop(0)
        with self.assertRaisesRegex(DesignError, "missing complete subprocess Workflow file"):
            validate_design(design)

    def test_recursive_dependency_graph_is_rejected(self):
        # Two individually valid graphs refer to one another with identical ports.
        design = copy.deepcopy(self.examples[0])
        first = design["workflows"][0]["workflow"]
        second = copy.deepcopy(first)
        for graph, target in [(first, "second.flow"), (second, "echo.flow")]:
            graph["nodes"].insert(1, {"id": "call", "type": "spawn_and_wait_subprocess",
                "name": "调用子进程",
                "x": 240, "y": 0,
                "arguments": {"workflow_file": target},
                "input_ports": copy.deepcopy(graph["input_ports"]),
                "output_ports": copy.deepcopy(graph["output_ports"])})
            graph["subprocess_workflow_files"] = [{"name": target,
                "input_ports": copy.deepcopy(graph["input_ports"]),
                "output_ports": copy.deepcopy(graph["output_ports"])}]
            graph["connections"] = [
                {"fromId": "input", "fromPortId": "control-out", "toId": "call", "toPortId": "control-in", "type": "control"},
                {"fromId": "call", "fromPortId": "control-out", "toId": "output", "toPortId": "control-in", "type": "control"},
                {"fromId": "input", "fromPortId": "workflow:text", "toId": "call", "toPortId": "workflow:text", "type": "content"},
                {"fromId": "call", "fromPortId": "workflow:content", "toId": "output", "toPortId": "workflow:content", "type": "content"}]
        design["workflows"].append({"filename": "second.flow", "workflow": second})
        with self.assertRaisesRegex(DesignError, "recursive subprocess Workflow file reference"):
            validate_design(design)

    def test_while_pop_is_accepted_with_context_input_and_loop_return(self):
        design = copy.deepcopy(self.examples[1])
        main = design["workflows"][-1]["workflow"]
        loop = next(n for n in main["nodes"] if n["id"] == "each")
        loop.update(type="while_pop", arguments={"value_type": "list-content"})
        edge = next(e for e in main["connections"] if e["toId"] == "each" and e["toPortId"] == "list-in")
        edge.update(fromId="store", fromPortId="context-id", toPortId="context-id", type="content")
        validate_workflow(main)
        validate_design(design)

    def test_json_tool_cannot_be_hidden_in_foreach_by_omitting_error_edge(self):
        design = copy.deepcopy(self.examples[1])
        main = design["workflows"][-1]["workflow"]
        design["workflows"] = [design["workflows"][-1]]
        main["subprocess_workflow_files"] = []
        call = next(n for n in main["nodes"] if n["id"] == "process")
        call.clear()
        call.update(id="process", type="json_tool", x=240, y=180)
        for edge in main["connections"]:
            if edge["toId"] == "process" and edge["type"] != "control":
                edge["toPortId"] = "arguments-json"
            if edge["fromId"] == "process" and edge["type"] != "control":
                edge["fromPortId"] = "result-json"
        main["nodes"].append({"id": "name", "type": "construct_content",
            "x": 480, "y": 180,
            "arguments": {"append_items": [{"type": "fixed", "value": "system.echo"}]}, "dataInputPorts": []})
        edge = next(e for e in main["connections"] if e["fromId"] == "empty" and e["type"] == "control")
        edge["toId"] = "name"
        main["connections"].extend([
            {"fromId": "name", "fromPortId": "control-out", "toId": "store", "toPortId": "control-in", "type": "control"},
            {"fromId": "name", "fromPortId": "content-out", "toId": "process", "toPortId": "tool-name", "type": "content"}])
        with self.assertRaisesRegex(ValueError, "branching control flow is not allowed inside foreach"):
            validate_design(design)

    def test_branch_outputs_may_not_merge(self):
        design = copy.deepcopy(self.examples[1])
        child = design["workflows"][0]["workflow"]
        # Sharing an Output is a merge even if branch values have the same type.
        edge = next(e for e in child["connections"] if e["fromId"] == "keep_text" and e["type"] == "control")
        edge["toId"] = "skip_output"
        with self.assertRaises(ValueError):
            validate_design(design)

    def test_data_cannot_flow_from_later_producer(self):
        design = copy.deepcopy(self.examples[0])
        graph = design["workflows"][0]["workflow"]
        graph["nodes"][1:1] = [
            {"id": "use", "type": "construct_content", "name": "使用数据", "x": 240, "y": 0, "arguments": {"append_items": [{"type": "port", "port_id": "text-in"}]}, "dataInputPorts": ["text-in"]},
            {"id": "produce", "type": "construct_content", "name": "生成数据", "x": 480, "y": 0, "arguments": {"append_items": [{"type": "fixed", "value": "late"}]}, "dataInputPorts": []}]
        graph["connections"] = [
            {"fromId": "input", "fromPortId": "control-out", "toId": "use", "toPortId": "control-in", "type": "control"},
            {"fromId": "use", "fromPortId": "control-out", "toId": "produce", "toPortId": "control-in", "type": "control"},
            {"fromId": "produce", "fromPortId": "control-out", "toId": "output", "toPortId": "control-in", "type": "control"},
            {"fromId": "produce", "fromPortId": "content-out", "toId": "use", "toPortId": "text-in", "type": "content"},
            {"fromId": "use", "fromPortId": "content-out", "toId": "output", "toPortId": "workflow:content", "type": "content"}]
        validate_workflow(graph)
        with self.assertRaisesRegex(DesignError, "data source must execute before target"):
            validate_design(design)

    def test_missing_model_id_is_rejected(self):
        design = copy.deepcopy(self.examples[0])
        graph = design["workflows"][0]["workflow"]
        graph["nodes"].insert(1, {"id": "llm", "type": "llm", "name": "模型调用", "x": 240, "y": 0, "arguments": {}})
        graph["connections"][0]["toId"] = "llm"
        graph["connections"].append({"fromId": "llm", "fromPortId": "control-out", "toId": "output", "toPortId": "control-in", "type": "control"})
        with self.assertRaisesRegex(DesignError, "llm requires a real model"):
            validate_design(design)

    def test_required_loop_input_is_not_allowed_to_remain_unwired(self):
        design = copy.deepcopy(self.examples[1])
        main = design["workflows"][-1]["workflow"]
        main["connections"] = [e for e in main["connections"]
                               if not (e["toId"] == "each" and e["toPortId"] == "list-in")]
        validate_workflow(main)
        with self.assertRaisesRegex(DesignError, "required data inputs missing"):
            validate_design(design)

    def test_router_internal_fallback_key_collision_is_rejected(self):
        design = copy.deepcopy(self.examples[1])
        child = design["workflows"][0]["workflow"]
        router = next(n for n in child["nodes"] if n["type"] == "router")
        router["arguments"]["branches"][0]["name"] = "$others"
        validate_workflow(child)
        with self.assertRaisesRegex(DesignError, "collides with fallback"):
            validate_design(design)

    def test_error_result_is_machine_readable_but_cannot_be_exported(self):
        error = {"format": "aagent.workflow-design/1", "status": "error", "entrypoint": None,
                 "workflows": [], "errors": [{"code": "MISSING_MODEL_ID", "message": "Provide an enabled model ID"}]}
        self.assertEqual(validate_design(error), [])
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(DesignError):
                export_design([], Path(folder) / "should-not-exist")
            self.assertFalse((Path(folder) / "should-not-exist").exists())

    def test_export_preserves_native_graphs_and_refuses_overwrite(self):
        items = validate_design(self.examples[1])
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / "native"
            export_design(items, out)
            for item in items:
                self.assertEqual(read_json(out / item["filename"]), item["workflow"])
            with self.assertRaises(FileExistsError):
                export_design(items, out)

    def test_json_rejects_duplicate_keys_and_nonfinite_constants(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "bad.json"
            for text in ['{"a":1,"a":2}', '{"a":NaN}']:
                path.write_text(text, encoding="utf-8")
                with self.subTest(text=text), self.assertRaises(DesignError):
                    read_json(path)

    def execute(self, design, inputs):
        docs = {i["filename"]: i["workflow"] for i in design["workflows"]}
        workflow = docs[design["entrypoint"]]
        graph = parse_workflow(workflow)
        start = next(i for i, n in enumerate(graph) if n["type"] == "input")
        graph[start]["_workflow_input_values"] = copy.deepcopy(inputs)
        for key, value in inputs.items():
            propagate_workflow_output(graph, graph[start], "workflow:" + key, value)
        memory = {}

        def create(owner, kind, value, context_id=None, definitions=None):
            key = context_id or f"ctx_test_{len(memory)}"
            memory[key] = copy.deepcopy(value)
            return key

        def read(key, *args, **kwargs):
            return copy.deepcopy(memory[key])

        def write(key, owner, kind, value, *args, **kwargs):
            memory[key] = copy.deepcopy(value)

        def delete(keys):
            for key in keys:
                memory.pop(key, None)

        with patch("workflow_parser._read_workspace_workflow_by_name", side_effect=lambda name: copy.deepcopy(docs[name])), \
             patch("workflow_context_repository.create_context", side_effect=create), \
             patch("workflow_context_repository.read_context", side_effect=read), \
             patch("workflow_context_repository.write_context", side_effect=write), \
             patch("workflow_context_repository.delete_contexts", side_effect=delete), \
             patch("workflow_run_repository.record_workflow_run"), \
             patch("terminal_repository.append_terminal_output") as append, \
             terminal_process_context("terminal-example"):
            output = run_workflow_map(graph, start)
        self.assertEqual(memory, {})
        return output, append

    def test_collection_executes_child_branches_and_aggregates(self):
        output, _ = self.execute(self.examples[1], {"items": ["a", "skip", "b"]})
        self.assertEqual(output, {"results": ["kept:a", "skipped", "kept:b"]})
        output, _ = self.execute(self.examples[1], {"items": []})
        self.assertEqual(output, {"results": []})

    def test_output_is_written_only_to_the_process_terminal(self):
        text = 'quoted "text"\nnew line \\ backslash'
        output, append = self.execute(self.examples[2], {"text": text})
        self.assertEqual(output, {"content": text})
        append.assert_called_once_with(text, terminal_process_id="terminal-example")


if __name__ == "__main__":
    unittest.main()
