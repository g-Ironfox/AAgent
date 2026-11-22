import json
import unittest
from unittest.mock import Mock, call, patch

import requests

from workflow_parser import WorkflowParseError, _read_workspace_workflow_record_by_name
from workflow_nodes import current_workflow_process


def echo_workflow():
    return {
        "schema_version": "2.0",
        "input_ports": [{"name": "content", "type": "content"}],
        "output_ports": [{"name": "content", "type": "content"}],
        "nodes": [
            {"id": "in", "type": "input", "workflowPorts": [
                {"id": "workflow:content", "name": "content", "type": "content"},
            ]},
            {"id": "out", "type": "output", "workflowPorts": [
                {"id": "workflow:content", "name": "content", "type": "content"},
            ]},
        ],
        "connections": [
            {"id": "control", "fromId": "in", "fromPortId": "control-out", "toId": "out", "toPortId": "control-in", "type": "control"},
            {"id": "data", "fromId": "in", "fromPortId": "workflow:content", "toId": "out", "toPortId": "workflow:content", "type": "content"},
        ],
    }


class WorkspaceWorkflowTest(unittest.TestCase):
    def setUp(self):
        token = current_workflow_process.set(None)
        self.addCleanup(current_workflow_process.reset, token)
        env = patch.dict("os.environ", {"WORKSPACE_API_URL": "http://workspace.test/"})
        env.start()
        self.addCleanup(env.stop)
        read = patch("workflow_parser.requests.get")
        self.read = read.start()
        self.addCleanup(read.stop)

    def response(self, payload, status=200):
        response = Mock(status_code=status)
        response.json.return_value = payload
        response.raise_for_status.return_value = None
        if status >= 400:
            response.raise_for_status.side_effect = requests.HTTPError(str(status))
        return response

    def listing(self, file_id="child-id"):
        return self.response({"items": [{"file_id": file_id, "name": "Child.flow"}]})

    def test_reader_uses_configured_workspace_api_and_exact_filename(self):
        workflow = echo_workflow()
        workflow["name"] = "different metadata name"
        self.read.side_effect = [self.response({"items": [
            {"file_id": "wrong-id", "name": "Other.flow"},
            {"file_id": "child-id", "name": "Child.flow"},
        ]}), self.response({"content": json.dumps(workflow)})]
        loaded, permissions = _read_workspace_workflow_record_by_name("Child.flow")
        self.assertEqual(loaded, workflow)
        self.assertEqual(permissions, {
            "runtime": {"read": 0, "write": 0}, "required": {"read": 0, "write": 0},
        })
        self.assertEqual(self.read.call_args_list, [
            call("http://workspace.test/api/files", headers={}, timeout=(3, 15)),
            call("http://workspace.test/api/files/child-id", headers={}, timeout=(3, 15)),
        ])

    def test_updates_and_checkpoint_restores_are_loaded_each_time(self):
        self.read.side_effect = [response for value in ("before", "edited", "restored")
                                for response in (self.listing(), self.response({
                                    "content": json.dumps({"description": value})}))]
        values = [_read_workspace_workflow_record_by_name("Child.flow")[0]["description"]
                  for _ in range(3)]
        self.assertEqual(values, ["before", "edited", "restored"])
        self.assertEqual(self.read.call_count, 6)

    def test_reader_rejects_ambiguous_exact_filename(self):
        self.read.return_value = self.response({"items": [
            {"file_id": "first", "name": "Child.flow"},
            {"file_id": "second", "name": "Child.flow"},
        ]})
        with self.assertRaisesRegex(WorkflowParseError, "filename is ambiguous: Child.flow"):
            _read_workspace_workflow_record_by_name("Child.flow")
        self.read.assert_called_once()

    def test_missing_or_unreadable_filename_is_not_loaded(self):
        self.read.return_value = self.response({"items": [
            {"file_id": "other", "name": "Other.flow"},
        ]})
        with self.assertRaisesRegex(WorkflowParseError, "not found or unreadable"):
            _read_workspace_workflow_record_by_name("Child.flow")
        self.read.assert_called_once()

    def test_deleted_file_returns_not_found_without_fallback(self):
        self.read.side_effect = [self.listing(), self.response({}, status=404)]
        with self.assertRaisesRegex(WorkflowParseError, "workflow file not found"):
            _read_workspace_workflow_record_by_name("Child.flow")
        self.assertEqual(self.read.call_count, 2)

    def test_denied_file_returns_permission_error(self):
        self.read.side_effect = [self.listing(), self.response({}, status=403)]
        with self.assertRaisesRegex(WorkflowParseError, "read permission denied"):
            _read_workspace_workflow_record_by_name("Child.flow")
        self.assertEqual(self.read.call_count, 2)

    def test_invalid_file_content_fails_clearly(self):
        for content in ("broken", "[]", "null", "123", 123, None):
            with self.subTest(content=content):
                self.read.side_effect = [self.listing(), self.response({"content": content})]
                with self.assertRaises(WorkflowParseError):
                    _read_workspace_workflow_record_by_name("Child.flow")

    def test_workspace_api_errors_fail_without_fallback(self):
        scenarios = [requests.ConnectionError("offline"),
                     [self.response({}, status=503)],
                     [self.listing(), self.response({}, status=503)]]
        for scenario in scenarios:
            with self.subTest(scenario=scenario):
                self.read.side_effect = scenario
                with self.assertRaisesRegex(WorkflowParseError, "failed to read workspace"):
                    _read_workspace_workflow_record_by_name("Child.flow")

    def test_file_id_is_url_encoded(self):
        self.read.side_effect = [self.listing("child/id with space"),
                                 self.response({"content": "{}"})]
        _read_workspace_workflow_record_by_name("Child.flow")
        self.assertEqual(self.read.call_args.args[0],
                         "http://workspace.test/api/files/child%2Fid%20with%20space")

    def test_permission_aware_reader_forwards_process_credential_and_metadata(self):
        token = current_workflow_process.set({"process_id": "p1", "_workspace_token": "secret"})
        self.addCleanup(current_workflow_process.reset, token)
        workflow = echo_workflow()
        permissions = {"runtime": {"read": 4, "write": 2},
                       "required": {"read": 1, "write": 1}}
        self.read.side_effect = [self.listing(), self.response({
            "content": json.dumps(workflow), "permissions": permissions,
        })]
        loaded, loaded_permissions = _read_workspace_workflow_record_by_name("Child.flow")
        self.assertEqual(loaded, workflow)
        self.assertEqual(loaded_permissions, permissions)
        for request in self.read.call_args_list:
            self.assertEqual(request.kwargs["headers"], {"X-AAgent-Process-ID": "p1:secret"})


if __name__ == "__main__":
    unittest.main()
