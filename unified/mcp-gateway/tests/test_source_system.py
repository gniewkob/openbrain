from __future__ import annotations

import unittest

from helpers import load_gateway_main


gateway = load_gateway_main()


class GatewaySourceSystemTests(unittest.TestCase):
    def test_normalize_brain_url_trims_and_removes_trailing_slash(self) -> None:
        self.assertEqual(
            gateway._normalize_brain_url("  https://openbrain.internal:7010/  "),
            "https://openbrain.internal:7010",
        )

    def test_normalize_brain_url_rejects_internal_whitespace(self) -> None:
        with self.assertRaisesRegex(ValueError, "BRAIN_URL"):
            gateway._normalize_brain_url("https://openbrain internal:7010")

    def test_normalize_source_system_trims_and_lowercases(self) -> None:
        self.assertEqual(
            gateway._normalize_source_system("  CoDeX_Agent-1  "),
            "codex_agent-1",
        )

    def test_normalize_source_system_rejects_invalid_value(self) -> None:
        with self.assertRaisesRegex(ValueError, "MCP_SOURCE_SYSTEM"):
            gateway._normalize_source_system("Bad Value!")
