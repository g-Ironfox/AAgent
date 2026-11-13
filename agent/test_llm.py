import unittest
from unittest.mock import patch

from llm import _thinking_options, chat_with_model


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


if __name__ == "__main__":
    unittest.main()
