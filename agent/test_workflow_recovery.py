"""Recovery plans follow ancestry, avoid duplicate attempts, and stop at stable."""
import unittest
from unittest.mock import Mock

from workflow_recovery import build_file_recovery_plan


class FileRecoveryPlanTest(unittest.TestCase):
    def plan(self, current="v3", stable="stable", diffs=None, seq=9):
        diffs = diffs or {}

        def read(method, path):
            self.assertEqual(method, "GET")
            if path == "/main":
                return {"content": current}
            if path == "/stable":
                return {"content": stable}
            return diffs[int(path.split("/")[2])]

        self.request = Mock(side_effect=read)
        return build_file_recovery_plan("main", "stable", seq, self.request)["versions"]

    def diff(self, parent, before=None, file_id="main"):
        return {"parent_seq": parent, "changes": [] if before is None else [{"file_id": file_id, "before_content": before}]}

    def test_ancestry_order_skips_duplicates_and_stops_at_stable(self):
        versions = self.plan(diffs={9: self.diff(7, "v3"), 7: self.diff(4, "v2"),
                                   4: self.diff(2, "v2"), 2: self.diff(1, "stable")})
        self.assertEqual(versions, [{"content": "v2", "checkpoint_seq": 4, "source": "checkpoint"},
                                    {"content": "stable", "checkpoint_seq": 1, "source": "stable"}])
        paths = [call.args[1] for call in self.request.call_args_list]
        self.assertNotIn("/checkpoints/8/diff", paths)
        self.assertNotIn("/checkpoints/1/diff", paths)

    def test_already_stable_has_no_retries_or_checkpoint_reads(self):
        self.assertEqual(self.plan(current="stable"), [])
        self.assertEqual(self.request.call_count, 2)

    def test_missing_older_file_content_falls_back_to_stable(self):
        versions = self.plan(diffs={9: self.diff(None)})
        self.assertEqual(versions, [{"content": "stable", "checkpoint_seq": 0, "source": "stable"}])

    def test_other_files_do_not_become_recovery_candidates(self):
        versions = self.plan(diffs={9: self.diff(None, "private text", file_id="other")})
        self.assertEqual([version["content"] for version in versions], ["stable"])

    def test_repeated_content_is_attempted_only_once(self):
        versions = self.plan(diffs={9: self.diff(6, "v2"), 6: self.diff(3, "v3"), 3: self.diff(None, "v2")})
        self.assertEqual([version["content"] for version in versions], ["v2", "stable"])

    def test_cyclic_ancestry_fails_instead_of_looping(self):
        with self.assertRaisesRegex(ValueError, "cycle"):
            self.plan(diffs={9: self.diff(6), 6: self.diff(9)})

    def test_invalid_sequence_fails_before_reading(self):
        for seq in (-1, True, 1.5, "1"):
            request = Mock()
            with self.subTest(seq=seq), self.assertRaises(ValueError):
                build_file_recovery_plan("main", "stable", seq, request)
            request.assert_not_called()

    def test_api_permission_errors_are_not_bypassed(self):
        request = Mock(side_effect=RuntimeError("HTTP 403"))
        with self.assertRaisesRegex(RuntimeError, "403"):
            build_file_recovery_plan("main", "stable", 9, request)
        self.assertEqual(request.call_count, 1)


if __name__ == "__main__":
    unittest.main()
