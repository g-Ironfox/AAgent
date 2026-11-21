"""Audit generated declarations against the live runtime, not a prose summary."""
import copy
import json
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from build_workflow_reference import (ROOT, REFERENCE_PATH, build_reference, schema_bundle,
                                      catalog, example_context)
from workflow_contract import SUPPORTED_NODE_TYPES, NODE_ARGUMENT_FIELDS_BY_TYPE
from jsonschema import Draft202012Validator, ValidationError


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

    def test_checked_in_markdown_matches_generator(self):
        self.assertEqual(REFERENCE_PATH.read_text(encoding="utf-8"), build_reference())
        self.assertEqual((HERE / "workflows/alfworld-agent-workflow-reference.md").read_text(encoding="utf-8"), build_reference())


if __name__ == "__main__":
    unittest.main()
