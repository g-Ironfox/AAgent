import importlib
import sys
import types
import unittest
from unittest.mock import Mock, patch


registered = {}
schemas = {}
fake_tool_module = types.ModuleType("tools.tool")


def fake_tool(description, parameters=None, name=None, output_schema=None):
    def register(function):
        tool_name = name or function.__name__
        registered[tool_name] = function
        schemas[tool_name] = {"parameters": parameters, "output_schema": output_schema}
        return function

    return register


fake_tool_module.tool = fake_tool
with patch.dict(sys.modules, {"tools.tool": fake_tool_module}):
    workspace_tools = importlib.import_module("tools.workspace")


class WorkspaceToolsTest(unittest.TestCase):
    def response(self, payload, status_code=200):
        response = Mock()
        response.ok = status_code < 400
        response.status_code = status_code
        response.json.return_value = payload
        return response

    def test_workspace_tools_register_local_crud_and_checkpoint_handlers(self):
        self.assertEqual(set(registered), {
            "workspace.list_files",
            "workspace.get_file",
            "workspace.create_file",
            "workspace.update_file",
            "workspace.delete_file",
            "workspace.list_checkpoints",
            "workspace.checkpoint_tree",
            "workspace.get_parent_checkpoint",
            "workspace.get_file_recovery_plan",
            "workspace.prepare_main_update",
            "workspace.checkpoint_diff",
            "workspace.create_checkpoint",
            "workspace.restore_checkpoint",
        })

    def test_main_candidate_tool_reads_with_acl_and_never_writes(self):
        current = {"name": "example-main.flow", "content": "{}", "revision": 3}
        expected = {"status": "rejected", "content": "", "error": "test", "name": current["name"], "revision": 3}
        with patch.object(workspace_tools, "_request", return_value=current) as request, \
                patch("workflow_evolution.prepare_main_update", return_value=expected) as prepare:
            actual = workspace_tools.prepare_workspace_main_update("main/id", 3, "candidate")
        self.assertEqual(actual, expected)
        request.assert_called_once_with("GET", "/main%2Fid")
        prepare.assert_called_once_with(current, 3, "candidate")

    @patch.dict("os.environ", {"WORKSPACE_API_URL": "http://workspace.test/"})
    def test_crud_tools_call_workspace_api(self):
        with patch.object(workspace_tools.requests, "request") as request:
            request.side_effect = [
                self.response({"items": [], "revision": 4}),
                self.response({"file_id": "a/b", "name": "note", "content": "x", "revision": 3}),
                self.response({"file_id": "new", "name": "note", "content": "x", "revision": 1}),
                self.response({"file_id": "a/b", "name": "note", "content": "y", "revision": 4}),
                self.response({"deleted": True, "file_id": "a/b"}),
            ]

            self.assertEqual(workspace_tools.list_workspace_files(), {"items": [], "revision": 4})
            self.assertEqual(workspace_tools.get_workspace_file("a/b")["file_id"], "a/b")
            workspace_tools.create_workspace_file("note", "x")
            workspace_tools.update_workspace_file("a/b", "note", "y", 3)
            workspace_tools.delete_workspace_file("a/b", 4)

            self.assertEqual(request.call_args_list[0].args[:2], ("GET", "http://workspace.test/api/files"))
            self.assertEqual(request.call_args_list[1].args[:2], ("GET", "http://workspace.test/api/files/a%2Fb"))
            self.assertEqual(request.call_args_list[2].kwargs["json"], {"name": "note", "content": "x"})
            self.assertEqual(request.call_args_list[3].kwargs["json"], {
                "name": "note", "content": "y", "revision": 3,
            })
            self.assertEqual(request.call_args_list[4].kwargs["params"], {"revision": 4})

    @patch.dict("os.environ", {"WORKSPACE_API_URL": "http://workspace.test/"})
    def test_checkpoint_tools_call_workspace_api_and_preserve_responses(self):
        payloads = [
            {"items": [{"seq": 4}], "has_more": True, "next_before_seq": 4},
            {"items": [{"seq": 4}], "head_seq": 4},
            {"seq": 4, "parent_seq": 2, "changes": [{"file_id": "note"}]},
            {"seq": 5, "type": "workspace.checkpoint", "data": {"name": "snapshot"}},
            {"seq": 6, "type": "workspace.restore", "data": {"checkpoint_seq": 4}},
        ]
        with patch.object(workspace_tools.requests, "request") as request:
            request.side_effect = [self.response(payload) for payload in payloads]
            results = [
                registered["workspace.list_checkpoints"](before_seq=9, limit=2, file_id="a/b"),
                registered["workspace.checkpoint_tree"](),
                registered["workspace.checkpoint_diff"](seq=4),
                registered["workspace.create_checkpoint"](name="snapshot"),
                registered["workspace.restore_checkpoint"](seq=4),
            ]
        self.assertEqual(results, payloads)
        self.assertEqual([call.args for call in request.call_args_list], [
            ("GET", "http://workspace.test/api/files/checkpoints"),
            ("GET", "http://workspace.test/api/files/checkpoints/tree"),
            ("GET", "http://workspace.test/api/files/checkpoints/4/diff"),
            ("POST", "http://workspace.test/api/files/checkpoints"),
            ("POST", "http://workspace.test/api/files/checkpoints/4/restore"),
        ])
        self.assertEqual(request.call_args_list[0].kwargs["params"], {
            "before_seq": 9, "limit": 2, "file_id": "a/b",
        })
        self.assertEqual(request.call_args_list[3].kwargs["json"], {"name": "snapshot"})

    def test_parent_checkpoint_uses_branch_ancestry_and_current_head(self):
        # A sibling with a larger sequence is not the current head's parent.
        tree = {"head_seq": 12, "items": [
            {"seq": 3, "data": {"parent_seq": None}},
            {"seq": 8, "data": {"parent_seq": 3}},
            {"seq": 12, "data": {"parent_seq": 3}},
            {"seq": 15, "data": {"parent_seq": 8}},
        ]}
        with patch.object(workspace_tools, "_request", return_value=tree) as request:
            self.assertEqual(registered["workspace.get_parent_checkpoint"](), {"seq": 12, "parent_seq": 3})
            self.assertEqual(registered["workspace.get_parent_checkpoint"](seq=15), {"seq": 15, "parent_seq": 8})
        self.assertTrue(all(call.args == ("GET", "/checkpoints/tree") for call in request.call_args_list))

    def test_parent_of_first_checkpoint_is_restorable_empty_workspace(self):
        for parent_seq in (None, 0):
            tree = {"head_seq": 3, "items": [{"seq": 3, "data": {"parent_seq": parent_seq}}]}
            with self.subTest(parent_seq=parent_seq), patch.object(workspace_tools, "_request", return_value=tree):
                self.assertEqual(workspace_tools.get_parent_workspace_checkpoint(), {"seq": 3, "parent_seq": 0})

    def test_empty_workspace_has_no_parent_even_when_other_branches_exist(self):
        for items in ([], [{"seq": 3, "data": {"parent_seq": None}}]):
            tree = {"head_seq": None, "items": items}
            with self.subTest(items=items), patch.object(workspace_tools, "_request", return_value=tree):
                self.assertEqual(workspace_tools.get_parent_workspace_checkpoint(), {"seq": 0, "parent_seq": None})
                self.assertEqual(workspace_tools.get_parent_workspace_checkpoint(0), {"seq": 0, "parent_seq": None})

    def test_missing_parent_lookup_checkpoint_is_reported(self):
        with patch.object(workspace_tools, "_request", return_value={"head_seq": None, "items": []}):
            with self.assertRaisesRegex(ValueError, "workspace checkpoint not found: 999"):
                workspace_tools.get_parent_workspace_checkpoint(999)

    def test_invalid_parent_lookup_sequence_fails_before_requesting_tree(self):
        for seq in (-1, "invalid", "1.5", 1.5, True):
            with self.subTest(seq=seq), patch.object(workspace_tools, "_request") as request:
                with self.assertRaises(ValueError):
                    workspace_tools.get_parent_workspace_checkpoint(seq)
                request.assert_not_called()

    def test_checkpoint_list_omits_unset_optional_filters(self):
        with patch.object(workspace_tools, "_request") as request:
            workspace_tools.list_workspace_checkpoints()
        request.assert_called_once_with("GET", "/checkpoints", params={"limit": 50})

    def test_checkpoint_zero_refers_to_empty_workspace(self):
        with patch.object(workspace_tools, "_request") as request:
            workspace_tools.get_workspace_checkpoint_diff(0)
            workspace_tools.restore_workspace_checkpoint(0)
        self.assertEqual([call.args for call in request.call_args_list], [
            ("GET", "/checkpoints/0/diff"), ("POST", "/checkpoints/0/restore"),
        ])

    def test_missing_checkpoint_is_reported(self):
        for handler in (workspace_tools.get_workspace_checkpoint_diff, workspace_tools.restore_workspace_checkpoint):
            with self.subTest(handler=handler.__name__), patch.object(workspace_tools.requests, "request") as request:
                request.return_value = self.response({"error": "Checkpoint not found"}, status_code=404)
                with self.assertRaisesRegex(ValueError, "workspace checkpoint not found"):
                    handler(999)

    def test_checkpoint_schemas_match_api_parameter_constraints(self):
        from jsonschema import Draft202012Validator, ValidationError
        cases = {
            "workspace.list_checkpoints": ({"limit": 100, "before_seq": 1}, [
                {"limit": 0}, {"limit": 101}, {"before_seq": 0}, {"unknown": True},
            ]),
            "workspace.checkpoint_tree": ({}, [{"seq": 1}]),
            "workspace.get_parent_checkpoint": ({"seq": 0}, [{"seq": -1}, {"unknown": True}]),
            "workspace.get_file_recovery_plan": ({"file_id": "main", "stable_file_id": "stable", "checkpoint_seq": 0},
                                                  [{}, {"file_id": "", "stable_file_id": "s", "checkpoint_seq": 1}]),
            "workspace.checkpoint_diff": ({"seq": 0}, [{}, {"seq": -1}]),
            "workspace.create_checkpoint": ({"name": "snapshot"}, [{}, {"name": ""}, {"name": "x" * 201}]),
            "workspace.restore_checkpoint": ({"seq": 0}, [{}, {"seq": -1}]),
        }
        for name, (valid, invalid) in cases.items():
            with self.subTest(tool=name):
                schema = schemas[name]
                Draft202012Validator.check_schema(schema["parameters"])
                Draft202012Validator.check_schema(schema["output_schema"])
                validator = Draft202012Validator(schema["parameters"])
                validator.validate(valid)
                if name == "workspace.get_parent_checkpoint":
                    validator.validate({})
                for value in invalid:
                    with self.assertRaises(ValidationError):
                        validator.validate(value)

    def test_revision_conflict_requires_rereading_file(self):
        with patch.object(workspace_tools.requests, "request") as request:
            request.return_value = self.response({"error": "revision conflict"}, status_code=409)
            with self.assertRaisesRegex(ValueError, "read the file again"):
                workspace_tools.update_workspace_file("file-1", "note", "new", 2)

    def test_workflow_requests_automatically_carry_process_credentials(self):
        from workflow_nodes import current_workflow_process

        token = current_workflow_process.set({"process_id": "p1", "_workspace_token": "secret"})
        self.addCleanup(current_workflow_process.reset, token)
        with patch.object(workspace_tools.requests, "request") as request:
            request.return_value = self.response({"error": "file read permission denied"}, status_code=403)
            with self.assertRaisesRegex(RuntimeError, "HTTP 403"):
                workspace_tools.get_workspace_file("private")

        self.assertEqual(request.call_args.kwargs["headers"], {"X-AAgent-Process-ID": "p1:secret"})
        self.assertNotIn("_workspace_token", schemas["workspace.get_file"]["parameters"]["properties"])

    def test_missing_file_is_reported(self):
        with patch.object(workspace_tools.requests, "request") as request:
            request.return_value = self.response({"error": "missing"}, status_code=404)
            with self.assertRaisesRegex(ValueError, "workspace file not found"):
                workspace_tools.get_workspace_file("missing")


if __name__ == "__main__":
    unittest.main()
