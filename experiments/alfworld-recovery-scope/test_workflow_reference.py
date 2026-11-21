"""Audit generated declarations against the live runtime, not a prose summary."""
import copy
import json
import re
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from build_workflow_reference import (ROOT, REFERENCE_PATH, build_reference, schema_bundle,
                                      catalog, example_context)
from workflow_contract import SUPPORTED_NODE_TYPES, NODE_ARGUMENT_FIELDS_BY_TYPE
from jsonschema import Draft202012Validator, ValidationError
from build_workflow_reference import SKILL_PATH
from workflow_validator import validate_workflow, WorkflowValidationError
from workflow_parser import parse_workflow


class ReferenceTest(unittest.TestCase):
    def test_every_runtime_node_has_a_schema_and_validated_examples(self):
        schema = schema_bundle()
        nodes = catalog(schema)  # Also validates every sample with the real _validate_node.
        self.assertEqual(set(nodes), SUPPORTED_NODE_TYPES)
        for kind, entry in nodes.items():
            self.assertEqual(set(entry["arguments"]), NODE_ARGUMENT_FIELDS_BY_TYPE[kind])
            validator = Draft202012Validator({"$defs": schema["$defs"], "$ref": entry["schema_ref"]})
            for sample in entry["examples"]:
                validator.validate(sample["node"])
            bad = copy.deepcopy(entry["examples"][0]["node"])
            bad["arguments"]["invented_argument"] = True
            with self.assertRaises(ValidationError):
                validator.validate(bad)
            bad = copy.deepcopy(entry["examples"][0]["node"])
            bad["type"] = "invented_node"
            with self.assertRaises(ValidationError):
                validator.validate(bad)

    def test_original_schema_is_not_rewritten(self):
        schema = schema_bundle()
        for key in [key for key in schema["$defs"] if key.startswith("node__")]:
            del schema["$defs"][key]
        expected = json.loads((ROOT / "agent/workflow_2_0.schema.json").read_text(encoding="utf-8"))
        self.assertEqual(schema, expected)

    def test_policies_and_dynamic_ports(self):
        nodes = catalog()
        self.assertEqual(nodes["tool"]["main_policy"], "preserve_existing_readers_only")
        self.assertEqual(nodes["llm"]["main_policy"], "existing_model_no_tool_calls")
        for kind in ("construct_tool", "session_write", "spawn_and_wait_subprocess", "read_terminal_queue"):
            self.assertEqual(nodes[kind]["main_policy"], "forbidden")
        llms = nodes["llm"]["examples"]
        self.assertEqual(set(llms[0]["accepted_data_connection_types"]["input"]), {"messages-in"})
        self.assertIn("tools-in", llms[2]["accepted_data_connection_types"]["input"])
        self.assertIn("branch$others", nodes["router"]["examples"][0]["control_out"])
        self.assertIn("fallback-in", nodes["struct_get"]["examples"][1]["accepted_data_connection_types"]["input"])
        self.assertEqual(nodes["list_length"]["examples"][0]["accepted_data_connection_types"]["output"]["length-out"], ["number"])

    def test_runtime_skill_examples_compile_and_legacy_nodes_are_rejected(self):
        examples = re.findall(r"```json\s*\n(.*?)\n```", SKILL_PATH.read_text(encoding="utf-8"), re.S)
        self.assertGreaterEqual(len(examples), 2)
        for encoded in examples:
            document = json.loads(encoded)
            validate_workflow(document)
            parse_workflow(document)
        legacy = (ROOT / "skills/workflow-json/SKILL.md").read_text(encoding="utf-8")
        self.assertNotIn(legacy, build_reference())
        sample = json.loads(examples[0])
        for obsolete in ("wait_terminal_event", "read_terminal_input"):
            bad = copy.deepcopy(sample)
            bad["nodes"][0]["type"] = obsolete
            with self.assertRaises(WorkflowValidationError):
                validate_workflow(bad)
        nodes = catalog()
        self.assertIn("read_terminal_queue", nodes)
        self.assertEqual(nodes["read_terminal_queue"]["examples"][0]["accepted_data_connection_types"]["output"]["list-out"], ["list-content"])

    def test_complete_skill_examples_execute_with_literal_values(self):
        from workflow_nodes import execute_node, propagate_workflow_output, WORKFLOW_END
        examples = [json.loads(text) for text in re.findall(r"```json\s*\n(.*?)\n```", SKILL_PATH.read_text(encoding="utf-8"), re.S)]
        observation = {"done": False, "reason": None, "text": r'C:\room\item; literal \n and "quotes"'}
        for document in examples:
            compiled = parse_workflow(document)
            entry = next(i for i, node in enumerate(compiled) if node["type"] == "input")
            name = document["input_ports"][0]["name"]
            value = observation["text"] if name == "value" else json.dumps({"observation": observation})
            propagate_workflow_output(compiled, compiled[entry], "workflow:" + name, value)
            current = entry
            for _ in range(len(compiled) + 1):
                if current == WORKFLOW_END:
                    break
                current = execute_node(current, compiled)
            self.assertEqual(current, WORKFLOW_END)
            output = next(n["_workflow_result"] for n in compiled if n["type"] == "output")
            if name == "value":
                self.assertEqual(output["value"], value)
            else:
                self.assertEqual(json.loads(output["value"]), observation)

    def test_checked_in_markdown_matches_generator(self):
        self.assertEqual(REFERENCE_PATH.read_text(encoding="utf-8"), build_reference())
        self.assertEqual((HERE / "workflows/alfworld-agent-workflow-reference.md").read_text(encoding="utf-8"), build_reference())


if __name__ == "__main__":
    unittest.main()
