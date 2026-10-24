from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from ecosim.llm import LLMConfig, extract_json


class LLMParsingTests(unittest.TestCase):
    def test_extract_json_plain(self):
        self.assertEqual(extract_json('{"action": "hold"}'), {"action": "hold"})

    def test_extract_json_fenced(self):
        text = '说明\n```json\n{"action": "invest", "equipment_key": "fertilizer_t0"}\n```\n'
        self.assertEqual(
            extract_json(text),
            {"action": "invest", "equipment_key": "fertilizer_t0"},
        )

    def test_config_from_env(self):
        with patch.dict(
            os.environ,
            {
                "ANTHROPIC_BASE_URL": "https://example.invalid/anthropic",
                "ANTHROPIC_AUTH_TOKEN": "local-test-token",
                "ANTHROPIC_MODEL": "test-model",
            },
            clear=False,
        ):
            config = LLMConfig.from_env()
        self.assertEqual(config.base_url, "https://example.invalid/anthropic")
        self.assertEqual(config.model, "test-model")


if __name__ == "__main__":
    unittest.main()
