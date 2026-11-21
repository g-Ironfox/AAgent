"""Keep regeneration from resetting a deployed ALFWorld bundle's bindings."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from build_alfworld_bundle import write_examples


class AlfworldGenerationTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.bindings = dict(model="enabled-model", experience_id="experience-id",
                             main_id="main-id", stable_id="stable-id")

    def snapshot(self):
        return {p.name: p.read_bytes() for p in self.folder.iterdir() if p.is_file()}

    def test_unbound_templates_can_be_regenerated(self):
        write_examples(self.folder)
        before = self.snapshot()
        write_examples(self.folder)
        self.assertEqual(self.snapshot(), before)

    def test_default_generation_cannot_reset_deployed_bindings(self):
        write_examples(self.folder, **self.bindings)
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, "Refusing to overwrite bound workflow"):
            write_examples(self.folder)
        self.assertEqual(self.snapshot(), before)

    def test_same_bindings_can_be_regenerated(self):
        write_examples(self.folder, **self.bindings)
        before = self.snapshot()
        write_examples(self.folder, **self.bindings)
        self.assertEqual(self.snapshot(), before)

    def test_all_files_are_checked_before_any_write(self):
        write_examples(self.folder)
        bootstrap = self.folder / "alfworld-agent-bootstrap.flow"
        document = json.loads(bootstrap.read_text(encoding="utf-8"))
        node = next(n for n in document["nodes"] if n["id"] == "recovery_plan_file_id")
        node["arguments"]["append_items"][0]["value"] = "deployed-main-id"
        bootstrap.write_text(json.dumps(document), encoding="utf-8")
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, "recovery_plan_file_id"):
            write_examples(self.folder)
        self.assertEqual(self.snapshot(), before)

    def test_force_is_required_to_reset_bound_templates(self):
        write_examples(self.folder, **self.bindings)
        write_examples(self.folder, force=True)
        doc = json.loads((self.folder / "alfworld-agent-main.flow").read_text(encoding="utf-8"))
        model = next(n for n in doc["nodes"] if n["id"] == "react")["arguments"]["model"]
        self.assertEqual(model, "REPLACE_WITH_MODEL_ID")

    def test_custom_prefix_binds_child_names_and_ids(self):
        write_examples(self.folder, prefix="alfworld-hard-paired", **self.bindings)
        doc = json.loads((self.folder / "alfworld-hard-paired-bootstrap.flow").read_text(encoding="utf-8"))
        values = {n["id"]: n.get("arguments", {}).get("append_items") for n in doc["nodes"]}
        self.assertEqual(values["main_name"][0]["value"], "alfworld-hard-paired-main.flow")
        self.assertEqual(values["iterator_name"][0]["value"], "alfworld-hard-paired-iterator.flow")
        self.assertEqual(values["recovery_plan_file_id"][0]["value"], "main-id")
        self.assertEqual(values["recovery_plan_stable_file_id"][0]["value"], "stable-id")


if __name__ == "__main__":
    unittest.main()
