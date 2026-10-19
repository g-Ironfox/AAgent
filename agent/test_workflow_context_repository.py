import json
import unittest
from unittest.mock import MagicMock, patch

from workflow_context_repository import (
    WorkflowContextError,
    create_context,
    delete_contexts,
    read_context,
    write_context,
)


class WorkflowContextRepositoryTest(unittest.TestCase):
    @patch("workflow_context_repository.get_connection")
    def test_create_stores_owner_type_value_and_ttl(self, get_connection):
        get_connection.return_value.eval.return_value = 1

        with patch("workflow_context_repository._ttl_seconds", return_value=60):
            context_id = create_context("invocation-1", "list-content", ["a", "b"])

        self.assertTrue(context_id.startswith("ctx_"))
        key = f"workflow-context:{context_id}"
        eval_args = get_connection.return_value.eval.call_args.args
        mapping = dict(zip(eval_args[3:-1:2], eval_args[4:-1:2]))
        self.assertEqual(eval_args[1:3], (1, key))
        self.assertEqual(mapping["value_type"], "list-content")
        self.assertEqual(json.loads(mapping["value"]), ["a", "b"])
        self.assertEqual(mapping["invocation_id"], "invocation-1")
        self.assertEqual(eval_args[-1], "60")

    @patch("workflow_context_repository.get_connection")
    def test_create_uses_custom_id_and_rejects_existing_id(self, get_connection):
        get_connection.return_value.eval.return_value = 1
        with patch("workflow_context_repository._ttl_seconds", return_value=60):
            self.assertEqual(
                create_context("invocation-1", "content", "value", "custom-id"),
                "custom-id",
            )
        get_connection.return_value.eval.return_value = 0
        with patch("workflow_context_repository._ttl_seconds", return_value=60):
            with self.assertRaisesRegex(WorkflowContextError, "Context ID 已存在"):
                create_context("invocation-1", "content", "value", "custom-id")

    @patch("workflow_context_repository.get_connection")
    def test_map_content_is_validated_and_stored(self, get_connection):
        get_connection.return_value.eval.return_value = 1
        with patch("workflow_context_repository._ttl_seconds", return_value=60):
            create_context("invocation-1", "map-content", {"done": "finished"})
        eval_args = get_connection.return_value.eval.call_args.args
        mapping = dict(zip(eval_args[3:-1:2], eval_args[4:-1:2]))
        self.assertEqual(mapping["value_type"], "map-content")
        self.assertEqual(json.loads(mapping["value"]), {"done": "finished"})
        for invalid in [{"": "empty"}, {"valid": 1}]:
            with self.subTest(invalid=invalid), self.assertRaises(WorkflowContextError):
                create_context("invocation-1", "map-content", invalid)

    @patch("workflow_context_repository.get_connection")
    def test_read_rejects_other_workflow_scope(self, get_connection):
        pipeline = MagicMock()
        pipeline.__enter__.return_value = pipeline
        pipeline.hgetall.return_value = {
            "value_type": "content",
            "value": '"secret"',
            "invocation_id": "invocation-1",
        }
        get_connection.return_value.pipeline.return_value = pipeline

        with self.assertRaisesRegex(WorkflowContextError, "Workflow Context 不存在"):
            read_context("ctx-one", "invocation-2", "content")

        pipeline.multi.assert_not_called()

    @patch("workflow_context_repository.get_connection")
    def test_read_rejects_mismatched_value_type(self, get_connection):
        pipeline = MagicMock()
        pipeline.__enter__.return_value = pipeline
        pipeline.hgetall.return_value = {
            "value_type": "content",
            "value": '"hello"',
            "invocation_id": "invocation-1",
        }
        get_connection.return_value.pipeline.return_value = pipeline

        with self.assertRaisesRegex(WorkflowContextError, "Workflow Context 类型不匹配"):
            read_context("ctx-one", "invocation-1", "message")

        pipeline.multi.assert_not_called()

    @patch("workflow_context_repository.get_connection")
    def test_read_returns_value_and_refreshes_ttl(self, get_connection):
        pipeline = MagicMock()
        pipeline.__enter__.return_value = pipeline
        pipeline.hgetall.return_value = {
            "value_type": "message",
            "value": '{"role":"user","content":"hello"}',
            "invocation_id": "invocation-1",
        }
        get_connection.return_value.pipeline.return_value = pipeline

        with patch("workflow_context_repository._ttl_seconds", return_value=90):
            value = read_context("ctx-one", "invocation-1", "message")

        self.assertEqual(value, {"role": "user", "content": "hello"})
        pipeline.multi.assert_called_once_with()
        pipeline.expire.assert_called_once_with("workflow-context:ctx-one", 90)
        pipeline.execute.assert_called_once_with()

    @patch("workflow_context_repository.get_connection")
    def test_write_overwrites_value_and_refreshes_ttl(self, get_connection):
        pipeline = MagicMock()
        pipeline.__enter__.return_value = pipeline
        pipeline.hgetall.return_value = {
            "value_type": "content",
            "value": '"before"',
            "invocation_id": "invocation-1",
        }
        get_connection.return_value.pipeline.return_value = pipeline

        with patch("workflow_context_repository._ttl_seconds", return_value=120):
            write_context("ctx-one", "invocation-1", "content", "after")

        mapping = pipeline.hset.call_args.kwargs["mapping"]
        self.assertEqual(json.loads(mapping["value"]), "after")
        pipeline.expire.assert_called_once_with("workflow-context:ctx-one", 120)
        pipeline.execute.assert_called_once_with()

    @patch("workflow_context_repository.get_connection")
    def test_delete_contexts_removes_all_registered_keys(self, get_connection):
        delete_contexts({"ctx-one", "ctx-two"})

        keys = set(get_connection.return_value.delete.call_args.args)
        self.assertEqual(
            keys,
            {"workflow-context:ctx-one", "workflow-context:ctx-two"},
        )

    @patch("workflow_context_repository.get_connection")
    def test_delete_contexts_skips_redis_for_empty_set(self, get_connection):
        delete_contexts(set())

        get_connection.assert_not_called()


if __name__ == "__main__":
    unittest.main()