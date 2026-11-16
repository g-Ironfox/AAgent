import json
import os
import unittest
from unittest.mock import call, patch

from pymongo.errors import PyMongoError

import task_worker
from workflow_parser import (
    WorkflowParseError,
    _read_workspace_workflow,
    _read_workspace_workflow_by_name,
)


def echo_workflow():
    return {
        "schema_version": "2.0", "name": "workspace echo",
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
        mongo = patch("workflow_parser.MongoClient")
        self.client = mongo.start()
        self.addCleanup(mongo.stop)
        self.database = self.client.return_value.__enter__.return_value.__getitem__.return_value
        self.workspace = self.database.__getitem__.return_value
        env = patch.dict(os.environ, {"MONGO_WORKSPACE_FILE_COLLECTION": "custom_workspace"})
        env.start()
        self.addCleanup(env.stop)

    def test_reader_uses_current_generation_and_custom_collection(self):
        workflow = echo_workflow()
        self.workspace.find_one.side_effect = [{"generation": 3}, {"content": json.dumps(workflow)}]
        self.assertEqual(_read_workspace_workflow("file-1"), workflow)
        self.database.__getitem__.assert_called_once_with("custom_workspace")
        self.workspace.find_one.assert_has_calls([
            call({"_id": "_workspace_current_state"}, {"generation": 1}),
            call({"_id": "3:file-1", "generation": 3}, {"content": 1}),
        ])

    def test_updates_and_checkpoint_restores_are_loaded_each_time(self):
        self.workspace.find_one.side_effect = [
            {"generation": 1}, {"content": '{"name":"before"}'},
            {"generation": 1}, {"content": '{"name":"edited"}'},
            {"generation": 2}, {"content": '{"name":"restored"}'},
        ]
        self.assertEqual([_read_workspace_workflow("file-1")["name"] for _ in range(3)],
                         ["before", "edited", "restored"])
        self.assertEqual(self.workspace.find_one.call_args.args[0], {"_id": "2:file-1", "generation": 2})

    def test_reader_resolves_exact_workspace_filename_not_workflow_metadata_name(self):
        workflow = echo_workflow()
        workflow["name"] = "different metadata name"
        self.workspace.find_one.side_effect = [
            {"generation": 3}, {"content": json.dumps(workflow)},
        ]

        self.assertEqual(_read_workspace_workflow_by_name("Child.flow"), workflow)
        self.workspace.find_one.assert_has_calls([
            call({"_id": "_workspace_current_state"}, {"generation": 1}),
            call({"name": "Child.flow", "generation": 3}, {"content": 1}),
        ])

    def test_deleted_file_is_not_read_from_other_generations(self):
        self.workspace.find_one.side_effect = [{"generation": 2}, None]
        with self.assertRaisesRegex(WorkflowParseError, "workflow file not found"):
            _read_workspace_workflow("file-1")
        self.assertEqual(self.workspace.find_one.call_count, 2)

    def test_invalid_file_content_fails_clearly(self):
        for content in ("broken", "[]", "null", 123, None):
            with self.subTest(content=content):
                self.workspace.find_one.side_effect = [{"generation": 1}, {"content": content}]
                with self.assertRaises(WorkflowParseError):
                    _read_workspace_workflow("file-1")

    def test_uninitialized_workspace_and_database_outage_fail(self):
        self.workspace.find_one.return_value = None
        with self.assertRaisesRegex(WorkflowParseError, "not initialized"):
            _read_workspace_workflow("file-1")
        self.workspace.find_one.side_effect = PyMongoError("down")
        with self.assertRaisesRegex(WorkflowParseError, "failed to read workspace"):
            _read_workspace_workflow("file-1")

    @patch("task_worker.record_history")
    @patch("task_worker.publish_to_queue")
    def test_file_executes_through_real_validation_parser_and_runner(self, publish, record):
        self.workspace.find_one.side_effect = [
            {"generation": 1}, {"content": json.dumps(echo_workflow())},
        ]
        task_worker.handle_task({
            "version": "1.1", "event_type": "workflow",
            "payload": {"workflow_file_id": "file-1", "content": "hello from workspace"},
        })
        publish.assert_called_once_with(task_worker.MAIN_AGENT_QUEUE_NAME, {
            "event_type": "response", "payload": {"content": "hello from workspace"},
        })


if __name__ == "__main__":
    unittest.main()
