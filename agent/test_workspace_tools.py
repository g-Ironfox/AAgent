import importlib
import sys
import types
import unittest
from unittest.mock import Mock, patch


registered = {}
fake_tool_module = types.ModuleType("tools.tool")


def fake_tool(description, parameters=None, name=None, output_schema=None):
    def register(function):
        registered[name or function.__name__] = function
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

    def test_workspace_tools_register_local_crud_handlers(self):
        self.assertEqual(set(registered), {
            "workspace.list_files",
            "workspace.get_file",
            "workspace.create_file",
            "workspace.update_file",
            "workspace.delete_file",
        })

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

    def test_revision_conflict_requires_rereading_file(self):
        with patch.object(workspace_tools.requests, "request") as request:
            request.return_value = self.response({"error": "revision conflict"}, status_code=409)
            with self.assertRaisesRegex(ValueError, "read the file again"):
                workspace_tools.update_workspace_file("file-1", "note", "new", 2)

    def test_missing_file_is_reported(self):
        with patch.object(workspace_tools.requests, "request") as request:
            request.return_value = self.response({"error": "missing"}, status_code=404)
            with self.assertRaisesRegex(ValueError, "workspace file not found"):
                workspace_tools.get_workspace_file("missing")


if __name__ == "__main__":
    unittest.main()
