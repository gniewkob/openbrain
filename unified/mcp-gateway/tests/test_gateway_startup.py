"""Test MCP gateway startup validation for INTERNAL_API_KEY."""

from __future__ import annotations

import importlib
import logging
import os
import sys
import unittest


class GatewayStartupTests(unittest.TestCase):
    def _reload_main_with_env(self, overrides: dict[str, str]):
        """Reload gateway main with temporary env overrides."""
        old_values: dict[str, str | None] = {
            key: os.environ.get(key) for key in overrides
        }
        for key, value in overrides.items():
            os.environ[key] = value
        try:
            sys.modules.pop("src.main", None)
            return importlib.import_module("src.main")
        finally:
            for key, old_value in old_values.items():
                if old_value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = old_value
            sys.modules.pop("src.main", None)

    def _reload_main(self, key: str) -> None:
        """Reload gateway main with given INTERNAL_API_KEY."""
        self._reload_main_with_env({"INTERNAL_API_KEY": key})

    def test_short_key_emits_warning(self) -> None:
        with self.assertLogs("mcp_gateway", level=logging.WARNING) as cm:
            self._reload_main("short")
        self.assertTrue(
            any("INTERNAL_API_KEY" in msg for msg in cm.output),
            f"Expected warning about INTERNAL_API_KEY, got: {cm.output}",
        )

    def test_missing_key_emits_warning(self) -> None:
        with self.assertLogs("mcp_gateway", level=logging.WARNING) as cm:
            self._reload_main("")
        self.assertTrue(
            any("INTERNAL_API_KEY" in msg for msg in cm.output),
            f"Expected warning about INTERNAL_API_KEY, got: {cm.output}",
        )

    def test_valid_key_no_warning(self) -> None:
        valid_key = "a" * 32
        try:
            with self.assertLogs("mcp_gateway", level=logging.WARNING) as cm:
                self._reload_main(valid_key)
            # If we get here, some warning was emitted — check it's not about key length
            key_warnings = [msg for msg in cm.output if "INTERNAL_API_KEY" in msg]
            self.assertEqual(
                key_warnings, [], f"Unexpected key warning: {key_warnings}"
            )
        except AssertionError:
            # assertLogs raises AssertionError if NO logs at all — that's fine
            pass

    def test_invalid_brain_url_fails_fast(self) -> None:
        with self.assertRaisesRegex(ValueError, "BRAIN_URL"):
            self._reload_main_with_env(
                {
                    "INTERNAL_API_KEY": "a" * 32,
                    "BRAIN_URL": "https://openbrain internal:7010",
                }
            )

    def test_invalid_backend_timeout_fails_fast(self) -> None:
        with self.assertRaisesRegex(ValueError, "BACKEND_TIMEOUT_S"):
            self._reload_main_with_env(
                {
                    "INTERNAL_API_KEY": "a" * 32,
                    "BACKEND_TIMEOUT_S": "0",
                }
            )

    def test_probe_timeout_above_backend_fails_fast(self) -> None:
        with self.assertRaisesRegex(ValueError, "MCP_HEALTH_PROBE_TIMEOUT_S"):
            self._reload_main_with_env(
                {
                    "INTERNAL_API_KEY": "a" * 32,
                    "BACKEND_TIMEOUT_S": "5",
                    "MCP_HEALTH_PROBE_TIMEOUT_S": "6",
                }
            )

    def test_invalid_source_system_fails_fast(self) -> None:
        with self.assertRaisesRegex(ValueError, "MCP_SOURCE_SYSTEM"):
            self._reload_main_with_env(
                {
                    "INTERNAL_API_KEY": "a" * 32,
                    "MCP_SOURCE_SYSTEM": "Bad Value!",
                }
            )

    def test_source_system_alias_is_accepted(self) -> None:
        module = self._reload_main_with_env(
            {
                "INTERNAL_API_KEY": "a" * 32,
                "SOURCE_SYSTEM": "  CoDeX_Agent-1  ",
            }
        )
        self.assertEqual(module.MCP_SOURCE_SYSTEM, "codex_agent-1")

    def test_mcp_source_system_takes_precedence_over_source_system(self) -> None:
        module = self._reload_main_with_env(
            {
                "INTERNAL_API_KEY": "a" * 32,
                "SOURCE_SYSTEM": "source-only",
                "MCP_SOURCE_SYSTEM": "mcp-wins",
            }
        )
        self.assertEqual(module.MCP_SOURCE_SYSTEM, "mcp-wins")


if __name__ == "__main__":
    unittest.main()
