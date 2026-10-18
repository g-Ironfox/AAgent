import unittest
from unittest.mock import patch

from pymongo.errors import PyMongoError

import task_worker
from workflow_parser import WorkflowParseError


class WorkerRoutingTest(unittest.TestCase):
    def test_event_version_must_match_before_history_or_routing(self):
        for event in (
            {"event_type": "terminal", "payload": {}},
            {"version": "1.0", "event_type": "terminal", "payload": {}},
        ):
            with self.subTest(event=event):
                with patch("task_worker.record_history") as record_history, patch(
                    "task_worker.read_bound_workflow_name"
                ) as read_bound:
                    with self.assertRaisesRegex(ValueError, "unsupported event version"):
                        task_worker.handle_task(event)
                    record_history.assert_not_called()
                    read_bound.assert_not_called()

    @patch("task_worker.read_bound_workflow_name", return_value=None)
    @patch("task_worker.record_history")
    def test_matching_event_version_is_recorded(self, record_history, read_bound):
        event = {"version": "1.1", "event_type": "terminal", "payload": {}}
        task_worker.handle_task(event)
        record_history.assert_called_once_with(event)
        read_bound.assert_called_once_with("terminal")

    @patch("task_worker.MongoClient")
    def test_binding_lookup_only_queries_enabled_event_type(self, mongo_client):
        database = mongo_client.return_value.__enter__.return_value.__getitem__.return_value
        database.__getitem__.return_value.find_one.return_value = {"workflow_name": "terminal workflow"}

        self.assertEqual(task_worker.read_bound_workflow_name("terminal"), "terminal workflow")
        database.__getitem__.return_value.find_one.assert_called_once_with(
            {"event_type": "terminal", "enabled": True}, {"workflow_name": 1}
        )
        database.__getitem__.assert_called_once_with("event_bindings")

    @patch("task_worker.MongoClient")
    def test_unbound_or_disabled_event_does_not_fall_back(self, mongo_client):
        database = mongo_client.return_value.__enter__.return_value.__getitem__.return_value
        database.__getitem__.return_value.find_one.return_value = None

        self.assertIsNone(task_worker.read_bound_workflow_name("terminal"))
        database.__getitem__.assert_called_once_with("event_bindings")

    @patch("task_worker.read_bound_workflow_name", return_value=None)
    @patch("task_worker.publish_to_queue")
    @patch("task_worker.record_history")
    def test_unbound_event_only_records_history(self, record_history, publish, read_bound):
        event = {"version": "1.1", "event_type": "custom.event", "payload": {"value": 1}}
        task_worker.handle_task(event)
        record_history.assert_called_once_with(event)
        read_bound.assert_called_once_with("custom.event")
        publish.assert_not_called()

    @patch("task_worker.read_bound_workflow_name", return_value="bound workflow")
    @patch("task_worker.publish_to_queue")
    @patch("task_worker.record_history")
    def test_bound_event_preserves_payload_but_overwrites_id(self, record_history, publish, read_bound):
        event = {"version": "1.1", "event_type": "custom.event", "payload": {"value": 1, "workflow_name": "untrusted"}}
        task_worker.handle_task(event)
        publish.assert_called_once_with(task_worker.MAIN_AGENT_QUEUE_NAME, {
            "event_type": "workflow", "payload": {"value": 1, "workflow_name": "bound workflow", "origin": event},
        })
        self.assertEqual(event["payload"]["workflow_name"], "untrusted")

    @patch("task_worker.read_bound_workflow_name", return_value=None)
    @patch("task_worker.publish_to_queue")
    @patch("task_worker.record_history")
    def test_unbound_response_and_error_only_record_history(self, record_history, publish, read_bound):
        for event_type in ("response", "error"):
            task_worker.handle_task({"version": "1.1", "event_type": event_type, "payload": {}})
        self.assertEqual(record_history.call_count, 2)
        self.assertEqual([call.args[0] for call in read_bound.call_args_list], ["response", "error"])
        publish.assert_not_called()

    @patch("task_worker.read_bound_workflow_name", return_value="self-workflow")
    @patch("task_worker.publish_to_queue")
    @patch("task_worker.record_history")
    def test_bound_response_and_error_trigger_workflow(self, record_history, publish, read_bound):
        for event_type in ("response", "error"):
            task_worker.handle_task({"version": "1.1", "event_type": event_type, "payload": {"text": event_type}})
        self.assertEqual([call.args[0] for call in read_bound.call_args_list], ["response", "error"])
        self.assertEqual([call.args[1] for call in publish.call_args_list], [
            {"event_type": "workflow", "payload": {"text": event_type, "workflow_name": "self-workflow", "origin": {"version": "1.1", "event_type": event_type, "payload": {"text": event_type}}}}
            for event_type in ("response", "error")
        ])

    @patch("task_worker.MongoClient")
    def test_binding_lookup_failure_is_not_treated_as_unbound(self, mongo_client):
        database = mongo_client.return_value.__enter__.return_value.__getitem__.return_value
        database.__getitem__.return_value.find_one.side_effect = PyMongoError("unavailable")
        with self.assertRaisesRegex(RuntimeError, "failed to read event binding"):
            task_worker.read_bound_workflow_name("terminal")

    @patch("task_worker._read_workflow")
    @patch("task_worker.validate_workflow")
    @patch("task_worker.parse_workflow")
    @patch("task_worker.propagate_workflow_output")
    @patch("task_worker.run_workflow_map", return_value={"content": "done"})
    @patch("task_worker.publish_to_queue")
    @patch("task_worker.record_history")
    def test_workflow_event_uses_id_and_optionally_exposes_it_as_input(
        self, record_history, publish, run, propagate, parse, validate, read_workflow
    ):
        read_workflow.return_value = {"name": "new workflow"}
        parse.return_value = [{"type": "input", "workflowPorts": [
            {"id": "name-in", "name": "workflow_name"}, {"id": "value-in", "name": "value"},
            {"id": "workflow:origin", "name": "origin"},
        ]}]
        event = {"version": "1.1", "event_type": "workflow", "payload": {"workflow_name": "selected", "value": 42}}
        task_worker.handle_task(event)
        read_workflow.assert_called_once_with("selected")
        self.assertEqual(propagate.call_count, 3)
        self.assertEqual(propagate.call_args_list[0].args[3], "selected")
        self.assertEqual(propagate.call_args_list[1].args[3], 42)
        self.assertEqual(propagate.call_args_list[2].args[3], event)
        self.assertEqual(publish.call_args.args[1]["event_type"], "response")

    @patch("task_worker._read_workflow", return_value={"name": "workflow"})
    @patch("task_worker.validate_workflow")
    @patch("task_worker.parse_workflow", return_value=[{"type": "input", "workflowPorts": []}])
    @patch("task_worker.propagate_workflow_output")
    @patch("task_worker.run_workflow_map", return_value={"content": "done"})
    @patch("task_worker.publish_to_queue")
    @patch("task_worker.record_history")
    def test_workflow_name_does_not_require_input_port(
        self, record_history, publish, run, propagate, parse, validate, read_workflow
    ):
        task_worker.handle_task({"version": "1.1", "event_type": "workflow", "payload": {"workflow_name": "selected"}})
        read_workflow.assert_called_once_with("selected")
        propagate.assert_not_called()
        self.assertEqual(publish.call_args.args[1]["event_type"], "response")

    @patch("task_worker._read_workflow", side_effect=WorkflowParseError("workflow not found: deleted"))
    @patch("task_worker.publish_to_queue")
    @patch("task_worker.record_history")
    def test_missing_workflow_publishes_error_once(self, record_history, publish, read_workflow):
        task_worker.handle_task({"version": "1.1", "event_type": "workflow", "payload": {"workflow_name": "deleted"}})
        publish.assert_called_once_with(task_worker.MAIN_AGENT_QUEUE_NAME, {
            "event_type": "error", "payload": {"workflow_name": "deleted", "message": "workflow not found"},
        })

    @patch("task_worker._read_workflow", side_effect=WorkflowParseError("workflow not found: bad"))
    @patch("task_worker.publish_to_queue")
    @patch("task_worker.record_history")
    def test_missing_workflow_name_publishes_not_found(self, record_history, publish, read_workflow):
        task_worker.handle_task({"version": "1.1", "event_type": "workflow", "payload": {"workflow_name": "bad"}})
        publish.assert_called_once_with(task_worker.MAIN_AGENT_QUEUE_NAME, {
            "event_type": "error", "payload": {"workflow_name": "bad", "message": "workflow not found"},
        })

    @patch("task_worker.time.sleep", side_effect=KeyboardInterrupt)
    @patch("task_worker.traceback.print_exc")
    @patch("task_worker.print")
    @patch("task_worker.set_worker_status")
    @patch("task_worker.publish_to_queue")
    @patch("task_worker.handle_task", side_effect=ValueError("node failed"))
    @patch("task_worker.pop_from_queue", return_value={"version": "1.1", "event_type": "workflow", "payload": {"workflow_name": "selected"}})
    def test_workflow_failure_publishes_error_and_resets_status(
        self, pop, handle, publish, set_status, log, print_exc, sleep
    ):
        with self.assertRaises(KeyboardInterrupt):
            task_worker.main()
        publish.assert_called_once_with(task_worker.MAIN_AGENT_QUEUE_NAME, {
            "event_type": "error",
            "payload": {"workflow_name": "selected", "message": "node failed"},
        })
        self.assertEqual(set_status.call_args.args[0]["state"], "idle")
        print_exc.assert_called_once()

    @patch("task_worker.time.sleep", side_effect=KeyboardInterrupt)
    @patch("task_worker.traceback.print_exc")
    @patch("task_worker.print")
    @patch("task_worker.set_worker_status")
    @patch("task_worker.publish_to_queue")
    @patch("task_worker.run_workflow_map", side_effect=ValueError("node failed"))
    @patch("task_worker.parse_workflow", return_value=[{"type": "input", "workflowPorts": []}])
    @patch("task_worker.validate_workflow")
    @patch("task_worker._read_workflow", return_value={"name": "example"})
    @patch("task_worker.record_history")
    @patch("task_worker.pop_from_queue", return_value={"version": "1.1", "event_type": "workflow", "payload": {"workflow_name": "selected"}})
    def test_node_failure_reaches_error_event(
        self, pop, record, read, validate, parse, run, publish, set_status, log, print_exc, sleep
    ):
        with self.assertRaises(KeyboardInterrupt):
            task_worker.main()
        publish.assert_called_once_with(task_worker.MAIN_AGENT_QUEUE_NAME, {
            "event_type": "error", "payload": {"workflow_name": "selected", "message": "node failed"},
        })

    @patch("task_worker.time.sleep", side_effect=KeyboardInterrupt)
    @patch("task_worker.traceback.print_exc")
    @patch("task_worker.print")
    @patch("task_worker.set_worker_status")
    @patch("task_worker.publish_to_queue")
    @patch("task_worker.read_bound_workflow_name", side_effect=RuntimeError("binding unavailable"))
    @patch("task_worker.record_history")
    @patch("task_worker.pop_from_queue", return_value={"version": "1.1", "event_type": "terminal", "payload": {}})
    def test_binding_failure_publishes_error_without_workflow_name(
        self, pop, record, read_bound, publish, set_status, log, print_exc, sleep
    ):
        with self.assertRaises(KeyboardInterrupt):
            task_worker.main()
        publish.assert_called_once_with(task_worker.MAIN_AGENT_QUEUE_NAME, {
            "event_type": "error", "payload": {"message": "binding unavailable"},
        })

    @patch("task_worker.time.sleep", side_effect=KeyboardInterrupt)
    @patch("task_worker.traceback.print_exc")
    @patch("task_worker.print")
    @patch("task_worker.set_worker_status")
    @patch("task_worker.publish_to_queue")
    @patch("task_worker.handle_task", side_effect=ValueError("error handler failed"))
    @patch("task_worker.pop_from_queue", return_value={"version": "1.1", "event_type": "error", "payload": {}})
    def test_failed_error_handler_does_not_publish_recursively(
        self, pop, handle, publish, set_status, log, print_exc, sleep
    ):
        with self.assertRaises(KeyboardInterrupt):
            task_worker.main()
        publish.assert_not_called()


if __name__ == "__main__":
    unittest.main()