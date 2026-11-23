import copy
import json
import unittest
from unittest.mock import Mock, patch

import requests

from llm import _prepare_tool_names, _thinking_options, chat_with_model, openai_llm_api


class ThinkingOptionsTest(unittest.TestCase):
    def test_think_enabled_leaves_provider_default_unchanged(self):
        self.assertEqual(_thinking_options({"provider": "Qwen"}, True), {})

    def test_think_disabled_uses_provider_specific_option(self):
        cases = [
            ({"provider": "Qwen", "model": "qwen3"}, {"enable_thinking": False}),
            ({"provider": "DeepSeek", "model": "deepseek-chat"}, {"thinking": {"type": "disabled"}}),
            ({"provider": "OpenAI", "model": "gpt-5"}, {"reasoning_effort": "none"}),
        ]
        for config, expected in cases:
            with self.subTest(provider=config["provider"]):
                self.assertEqual(_thinking_options(config, False), expected)

    def test_chat_with_model_passes_thinking_option_to_request(self):
        config = {
            "provider": "Qwen",
            "model": "qwen3",
            "base_url": "https://example.test/v1",
            "api_key": "secret",
        }
        with patch("llm._model_config", return_value=config), patch(
            "llm.openai_llm_api", return_value=("answer", "unexpected reasoning", [])
        ) as request:
            result = chat_with_model([], "model-id", tools=[], think=False)

        self.assertEqual(result, ("answer", "", []))
        request.assert_called_once_with(
            [], "qwen3", "https://example.test/v1", "secret", [],
            extra={"enable_thinking": False},
        )



class ToolCallCompatibilityTest(unittest.TestCase):
    def schema(self, name):
        return {"type": "function", "function": {
            "name": name, "parameters": {"type": "object", "properties": {}},
        }}

    def response(self, tool_calls=None):
        response = Mock(status_code=200)
        response.json.return_value = {"choices": [{"message": {
            "content": "answer", "tool_calls": tool_calls or [],
        }}]}
        return response

    def test_internal_names_are_legal_distinct_and_do_not_mutate_inputs(self):
        names = ["workspace.get_file", "workspace_get_file", "documents.query_by_name", "x" * 100]
        source = {"tools": [self.schema(name) for name in names], "messages": []}
        original = copy.deepcopy(source)
        payload, restored = _prepare_tool_names(source)
        aliases = [tool["function"]["name"] for tool in payload["tools"]]
        for alias in aliases:
            self.assertRegex(alias, r"^[A-Za-z0-9_-]{1,64}$")
        self.assertEqual(len(set(aliases)), len(names))
        self.assertEqual(aliases[1], "workspace_get_file")
        self.assertEqual([restored.get(alias, alias) for alias in aliases], names)
        self.assertEqual(source, original)
        self.assertEqual(_prepare_tool_names(source), (payload, restored))

    def test_alias_is_shared_by_tool_schema_history_and_tool_choice(self):
        source = {
            "tools": [self.schema("workspace.get_file")],
            "messages": [
                {"role": "assistant", "content": None, "tool_calls": [{
                    "id": "call-1", "type": "function", "function": {
                        "name": "workspace.get_file", "arguments": '{"file_id":"abc"}',
                    },
                }]},
                {"role": "tool", "tool_call_id": "call-1", "name": "workspace.get_file", "content": "result"},
            ],
            "tool_choice": {"type": "function", "function": {"name": "workspace.get_file"}},
        }
        payload, _ = _prepare_tool_names(source)
        alias = payload["tools"][0]["function"]["name"]
        self.assertEqual(payload["messages"][0]["tool_calls"][0]["function"]["name"], alias)
        self.assertEqual(payload["messages"][1]["name"], alias)
        self.assertEqual(payload["tool_choice"]["function"]["name"], alias)
        self.assertEqual(payload["messages"][1]["tool_call_id"], "call-1")

    def test_call_results_restore_original_names_before_tool_dispatch(self):
        tools = [self.schema("workspace.get_file"), self.schema("tavily_search")]
        messages = [{"role": "user", "content": "Find a file"}]
        original = copy.deepcopy(tools)
        def post(*args, **kwargs):
            schemas = kwargs["json"]["tools"]
            return self.response([{
                "id": "call-1", "type": "function", "function": {
                    "name": schemas[0]["function"]["name"], "arguments": '{"file_id":"abc"}',
                },
            }])
        with patch("llm.requests.post", side_effect=post) as request:
            content, reasoning, calls = openai_llm_api(messages, "deepseek-flash", "https://example.test", "secret", tools)
        self.assertEqual(calls[0]["function"]["name"], "workspace.get_file")
        self.assertEqual(json.loads(calls[0]["function"]["arguments"]), {"file_id": "abc"})
        self.assertEqual(calls[0]["id"], "call-1")
        self.assertEqual(tools, original)
        self.assertEqual((content, reasoning), ("answer", ""))
        self.assertNotIn(".", request.call_args.kwargs["json"]["tools"][0]["function"]["name"])

    def test_provider_indexes_are_removed_without_mutating_response_or_call_details(self):
        calls = [
            {"index": 0, "id": "read-call", "type": "function", "function": {
                "name": "read_file", "arguments": '{ "file_id": "a.b" }',
            }},
            {"index": 1, "id": "human-call", "type": "function", "function": {
                "name": "ask_human", "arguments": '{"question":"Which file?"}',
            }},
        ]
        before = copy.deepcopy(calls)
        response = self.response(calls)
        with patch("llm.requests.post", return_value=response):
            _, _, normalized = openai_llm_api(
                [], "model", "https://example.test/v1", "secret", [],
            )
        self.assertEqual(normalized, [
            {key: value for key, value in call.items() if key != "index"}
            for call in before
        ])
        self.assertEqual(response.json.return_value["choices"][0]["message"]["tool_calls"], before)
        self.assertEqual(calls, before)

    def test_alias_collision_preserves_real_name_and_is_independent_of_tool_order(self):
        source = {"tools": [self.schema("workspace.get_file")], "messages": []}
        payload, _ = _prepare_tool_names(source)
        occupied = payload["tools"][0]["function"]["name"]
        source["tools"].append(self.schema(occupied))
        payload, restored = _prepare_tool_names(source)
        aliases = [tool["function"]["name"] for tool in payload["tools"]]
        self.assertNotEqual(aliases[0], occupied)
        self.assertEqual(aliases[1], occupied)
        self.assertEqual(restored[aliases[0]], "workspace.get_file")
        source["tools"].reverse()
        reordered, reordered_map = _prepare_tool_names(source)
        self.assertEqual(reordered_map, restored)
        self.assertEqual([t["function"]["name"] for t in reordered["tools"]], aliases[::-1])

    def test_restored_names_survive_a_second_api_request_with_tool_history(self):
        tools = [self.schema("workspace.get_file")]
        messages = [{"role": "user", "content": "Read a file"}]
        arguments = '{"file_id":"a.b","name":"workspace.get_file"}'
        def post(*args, **kwargs):
            payload = kwargs["json"]
            alias = payload["tools"][0]["function"]["name"]
            if len(payload["messages"]) == 1:
                return self.response([{"id": "call-1", "type": "function", "function": {
                    "name": alias, "arguments": arguments,
                }}])
            self.assertEqual(payload["messages"][1]["tool_calls"][0]["function"], {
                "name": alias, "arguments": arguments,
            })
            self.assertEqual(payload["messages"][2]["tool_call_id"], "call-1")
            self.assertEqual(payload["messages"][2]["content"], "file text")
            return self.response()
        with patch("llm.requests.post", side_effect=post):
            _, _, calls = openai_llm_api(messages, "deepseek-flash", "https://example.test", "secret", tools)
            messages.append({"role": "assistant", "content": None, "tool_calls": calls})
            messages.append({"role": "tool", "tool_call_id": "call-1", "content": "file text"})
            self.assertEqual(openai_llm_api(messages, "deepseek-flash", "https://example.test", "secret", tools), ("answer", "", []))
        self.assertEqual(calls[0]["function"]["name"], "workspace.get_file")
        self.assertEqual(calls[0]["function"]["arguments"], arguments)

    def test_workflow_llm_results_dispatch_to_real_local_and_remote_names(self):
        from types import SimpleNamespace
        from workflow_nodes import workflow_json_tool, workflow_llm
        for name, kind in [("workspace.get_file", "local"), ("documents.query_by_name", "remote")]:
            with self.subTest(tool=name):
                arguments = {"query": "a.b", "label": "workspace.get_file"}
                schema = self.schema(name)
                registry = SimpleNamespace(
                    registered_tools=[schema] if kind == "local" else [],
                    tool_handlers={name: object()} if kind == "local" else {},
                    execute_tool=Mock(return_value={"result": "local"}),
                )
                config = {"provider": "DeepSeek", "model": "deepseek-flash", "base_url": "https://example.test", "api_key": "secret"}
                nodes = [{
                    "id": "choose-tool", "type": "llm", "arguments": {"model": "model-id", "think": False},
                    "_metadata_tools": [{"name": name, "kind": kind}],
                    "successors": {"next": 1},
                    "data_inputs": {"messages-in": [None, None, ['{"role":"user","content":"Find a file"}']]},
                    "data_outputs": {"tool_calls": [[1, "calls"]]},
                }, {"data_inputs": {"calls": [0, "tool_calls", None]}}]
                def post(*args, **kwargs):
                    alias = kwargs["json"]["tools"][0]["function"]["name"]
                    self.assertNotEqual(alias, name)
                    return self.response([{"id": "call-1", "type": "function", "function": {
                        "name": alias, "arguments": json.dumps(arguments),
                    }}])
                with patch.dict("sys.modules", {"tools.tool": registry}), \
                     patch("llm._model_config", return_value=config), \
                     patch("llm.requests.post", side_effect=post), \
                     patch("tool_server_client.get_remote_tool_schemas", return_value=[schema]), \
                     patch("tool_server_client.call_remote_tool", return_value={"result": "remote"}) as remote:
                    self.assertEqual(workflow_llm(0, nodes), 1)
                    call = json.loads(nodes[1]["data_inputs"]["calls"][2][0])
                    self.assertEqual(call["function"]["name"], name)
                    dispatch = [{
                        "id": "invoke", "successors": {"next": 1},
                        "data_inputs": {"tool-name": [None, None, call["function"]["name"]],
                                        "arguments-json": [None, None, call["function"]["arguments"]]},
                        "data_outputs": {"result-json": [[1, "result"]]},
                    }, {"data_inputs": {"result": [0, "result-json", None]}}]
                    self.assertEqual(workflow_json_tool(0, dispatch), 1)
                if kind == "local":
                    registry.execute_tool.assert_called_once_with("invoke", name, arguments, preserve_result=True)
                    remote.assert_not_called()
                else:
                    remote.assert_called_once()
                    self.assertEqual(remote.call_args.args[:3], (name, arguments, "wait"))
                    registry.execute_tool.assert_not_called()
                self.assertEqual(json.loads(dispatch[1]["data_inputs"]["result"][2]), {"result": kind})

    def test_http_error_includes_provider_message_and_redacts_key(self):
        response = Mock(status_code=400)
        response.raise_for_status.side_effect = requests.HTTPError("400 Bad Request", response=response)
        response.json.return_value = {"error": {"message": "Invalid function name; secret-key", "param": "tools[0].function.name"}}
        with patch("llm.requests.post", return_value=response):
            with self.assertRaises(requests.HTTPError) as raised:
                openai_llm_api([], "deepseek-flash", "https://example.test", "secret-key", [])
        self.assertIn("Invalid function name", str(raised.exception))
        self.assertIn("tools[0].function.name", str(raised.exception))
        self.assertNotIn("secret-key", str(raised.exception))
        self.assertIs(raised.exception.response, response)

    def test_non_json_error_body_is_reported_and_bounded(self):
        response = Mock(status_code=502, text="proxy failure " + "x" * 4000)
        response.raise_for_status.side_effect = requests.HTTPError("502 Bad Gateway", response=response)
        response.json.side_effect = ValueError("not JSON")
        with patch("llm.requests.post", return_value=response):
            with self.assertRaisesRegex(requests.HTTPError, "proxy failure") as raised:
                openai_llm_api([], "deepseek-flash", "https://example.test", "secret", [])
        self.assertLess(len(str(raised.exception)), 2100)

    def test_no_tools_and_balance_response_remain_supported(self):
        for status in (200, 402):
            response = self.response()
            response.status_code = status
            with patch("llm.requests.post", return_value=response) as request:
                result = openai_llm_api([], "deepseek-flash", "https://example.test", "secret", [])
            self.assertEqual(request.call_args.kwargs["json"]["tools"], [])
            self.assertEqual(result, (402, None, None) if status == 402 else ("answer", "", []))


if __name__ == "__main__":
    unittest.main()
