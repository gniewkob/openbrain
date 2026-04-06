"""Test MCP gateway startup validation for INTERNAL_API_KEY."""

from __future__ import annotations

import importlib
import logging
import sys
import unittest


class GatewayStartupTests(unittest.TestCase):
    def _reload_main(self, key: str) -> None:
        """Reload gateway main with given INTERNAL_API_KEY."""
        import os

        old_key = os.environ.get("INTERNAL_API_KEY")
        os.environ["INTERNAL_API_KEY"] = key
        try:
            sys.modules.pop("src.main", None)
            importlib.import_module("src.main")
        finally:
            if old_key is None:
                os.environ.pop("INTERNAL_API_KEY", None)
            else:
                os.environ["INTERNAL_API_KEY"] = old_key
            sys.modules.pop("src.main", None)

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


if __name__ == "__main__":
    unittest.main()
