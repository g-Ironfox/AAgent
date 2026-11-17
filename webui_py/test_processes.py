import json
import unittest
from unittest.mock import MagicMock, patch

from fastapi.responses import JSONResponse

from file_store import FileMissingError
from processes import CreateProcessRequest, create_processes_router
from redis.exceptions import ConnectionError as RedisConnectionError
from pymongo.errors import ServerSelectionTimeoutError


def workflow_document():
    return {
        "schema_version": "2.0", "name": "Example",
        "input_ports": [{"name": "text", "type": "content"}],
        "output_ports": [{"name": "text", "type": "content"}],
        "nodes": [
            {"id": "out", "type": "output", "workflowPorts": [
                {"id": "workflow:text", "name": "text", "type": "content"}
            ]},
            {"id": "in", "type": "input", "workflowPorts": [
                {"id": "workflow:text", "name": "text", "type": "content"}
            ]},
        ],
        "connections": [
            {"fromId": "in", "fromPortId": "control-out", "toId": "out",
             "toPortId": "control-in", "type": "control"},
            {"fromId": "in", "fromPortId": "workflow:text", "toId": "out",
             "toPortId": "workflow:text", "type": "content"},
        ],
        "metadata": {"structs": []},
    }



class ProcessCreationApiTest(unittest.TestCase):
    def setUp(self):
        self.redis = MagicMock()
        self.store = MagicMock()
        self.logs = MagicMock()
        router = create_processes_router(self.redis, self.store, self.logs)
        self.create = next(route.endpoint for route in router.routes if route.path == "/api/processes")
        self.workflow_options = next(
            route.endpoint for route in router.routes
            if route.path == "/api/processes/workflow-options"
        )

    def test_workflow_options_are_listed_without_event_bindings(self):
        valid = workflow_document()
        self.store.list_files.return_value = [
            {"file_id": "file-1", "name": "demo.json"},
            {"file_id": "invalid", "name": "invalid.json"},
        ]
        self.store.get_file.side_effect = [
            {"file_id": "file-1", "name": "demo.json", "content": json.dumps(valid)},
            {"file_id": "invalid", "name": "invalid.json", "content": "not json"},
        ]

        result = self.workflow_options()

        self.assertEqual(result["items"], [{
            "file_id": "file-1", "name": "demo.json", "workflow_name": "Example",
            "input_ports": valid["input_ports"], "output_ports": valid["output_ports"],
        }])

    @patch("processes.initialize_process_pair")
    @patch("processes.build_workflow_process")
    def test_creation_stores_pair_and_schedules_process(self, build, initialize):
        process = {
            "process_id": "p1", "parent_process_id": "user_interface",
            "workflow_name": "Example", "workflow": "[]", "current_node_id": 0,
            "status": "ready", "terminal_process_id": "t1",
            "start_time": "2026-11-17T00:00:00+00:00",
        }
        terminal = {
            "process_id": "t1", "process_type": "terminal", "parent_process_id": "p1",
            "start_time": process["start_time"], "status": "waiting_for_input",
            "wait_for": {"kind": "terminal_message"},
        }
        build.return_value = process
        initialize.return_value = terminal
        self.store.get_file.return_value = {"content": '{"schema_version":"2.0"}'}

        result = self.create(CreateProcessRequest(workflow_file_id="file1", inputs={"text": "hello"}))

        build.assert_called_once_with({"schema_version": "2.0"}, {"text": "hello"}, "file1")
        pipeline = self.redis.pipeline.return_value.__enter__.return_value
        pipeline.hset.assert_called_once()
        _, kwargs = pipeline.hset.call_args
        self.assertEqual(set(kwargs["mapping"]), {"p1", "t1"})
        self.assertEqual(json.loads(kwargs["mapping"]["p1"])["parent_process_id"], "user_interface")
        pipeline.srem.assert_called_once()
        pipeline.lpush.assert_called_once()
        pipeline.execute.assert_called_once()
        self.assertEqual(result["terminal_process_id"], "t1")
        self.logs.update_one.assert_called_once()

    def test_invalid_input_does_not_write_to_redis(self):
        self.store.get_file.return_value = {"content": "{}"}
        with patch("processes.build_workflow_process", side_effect=ValueError("invalid workflow")):
            result = self.create(CreateProcessRequest(workflow_file_id="f1"))
        self.assertIsInstance(result, JSONResponse)
        self.assertEqual(result.status_code, 400)
        self.redis.pipeline.assert_not_called()

    def test_missing_workflow_returns_not_found(self):
        self.store.get_file.side_effect = FileMissingError("missing")
        result = self.create(CreateProcessRequest(workflow_file_id="f1"))
        self.assertEqual(result.status_code, 404)
        self.redis.pipeline.assert_not_called()

    def test_full_compilation_initializes_runnable_workflow_and_terminal(self):
        from workflow_nodes import execute_node
        self.store.get_file.return_value = {"content": json.dumps(workflow_document())}
        result = self.create(CreateProcessRequest(workflow_file_id="file1", inputs={"text": "hello"}))
        self.assertIsInstance(result, dict)
        pipeline = self.redis.pipeline.return_value.__enter__.return_value
        records = pipeline.hset.call_args.kwargs["mapping"]
        process = json.loads(records[result["process_id"]])
        terminal = json.loads(records[result["terminal_process_id"]])
        self.assertEqual(process["parent_process_id"], "user_interface")
        self.assertEqual(process["current_node_id"], 1)
        self.assertEqual(process["status"], "ready")
        self.assertEqual(terminal["parent_process_id"], process["process_id"])
        self.assertEqual(terminal["start_time"], process["start_time"])
        workflow = json.loads(process["workflow"])
        self.assertEqual(workflow[0]["data_inputs"]["workflow:text"][2], "hello")
        self.assertEqual(execute_node(process["current_node_id"], workflow), 0)
        self.assertEqual(execute_node(0, workflow), -1)
        self.assertEqual(workflow[0]["_workflow_result"], {"text": "hello"})
        pipeline.lpush.assert_called_once_with("ready_processes", process["process_id"])

    def test_bad_workflows_and_input_values_are_rejected_before_persistence(self):
        cases = [
            ("not json", {}), ("[]", {}), ("{}", {}),
            (json.dumps(workflow_document()), {"unknown": "value"}),
            (json.dumps(workflow_document()), {"text": 42}),
        ]
        for content, inputs in cases:
            with self.subTest(content=content, inputs=inputs):
                self.store.get_file.return_value = {"content": content}
                result = self.create(CreateProcessRequest(workflow_file_id="file1", inputs=inputs))
                self.assertEqual(result.status_code, 400)
        self.redis.pipeline.assert_not_called()
        self.logs.update_one.assert_not_called()

    def test_redis_failure_returns_service_unavailable(self):
        self.store.get_file.return_value = {"content": json.dumps(workflow_document())}
        pipeline = self.redis.pipeline.return_value.__enter__.return_value
        pipeline.execute.side_effect = RedisConnectionError("offline")
        with self.assertLogs("processes", level="ERROR"):
            result = self.create(CreateProcessRequest(workflow_file_id="file1"))
        self.assertEqual(result.status_code, 503)
        self.logs.update_one.assert_not_called()

    def test_timing_failure_does_not_hide_successful_creation(self):
        self.store.get_file.return_value = {"content": json.dumps(workflow_document())}
        self.logs.update_one.side_effect = ServerSelectionTimeoutError("offline")
        with self.assertLogs("processes", level="ERROR"):
            result = self.create(CreateProcessRequest(workflow_file_id="file1"))
        self.assertEqual(result["status"], "ready")
        self.redis.pipeline.return_value.__enter__.return_value.execute.assert_called_once()
