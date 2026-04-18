from __future__ import annotations

import unittest

from src import mcp_transport_utils as utils


class _FakeLogger:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, str]]] = []

    def error(self, event: str, **kwargs) -> None:
        self.events.append((event, kwargs))


class McpTransportUtilsTests(unittest.IsolatedAsyncioTestCase):
    async def test_make_tool_guard_rewraps_exceptions(self) -> None:
        logger = _FakeLogger()
        guard = utils.make_tool_guard(logger)

        @guard
        async def broken():
            raise RuntimeError("boom")

        with self.assertRaisesRegex(ValueError, "Tool execution failed: boom"):
            await broken()
        self.assertEqual(len(logger.events), 1)
        self.assertEqual(logger.events[0][0], "mcp_tool_error")
        self.assertEqual(logger.events[0][1]["tool"], "broken")

    async def test_extract_record_from_write_response_validates_shape(self) -> None:
        with self.assertRaisesRegex(
            ValueError, "Write response missing record payload"
        ):
            utils.extract_record_from_write_response({"status": "ok"}, lambda rec: rec)

    async def test_redact_logged_payload_redacts_nested_fields(self) -> None:
        payload = {
            "content": "secret",
            "nested": {"title": "sensitive", "keep": "ok"},
            "items": [{"match_key": "x"}, {"keep": "y"}],
        }
        redacted = utils.redact_logged_payload(
            payload,
            {"content", "title", "match_key"},
        )
        self.assertEqual(redacted["content"], "[REDACTED]")
        self.assertEqual(redacted["nested"]["title"], "[REDACTED]")
        self.assertEqual(redacted["nested"]["keep"], "ok")
        self.assertEqual(redacted["items"][0]["match_key"], "[REDACTED]")
        self.assertEqual(redacted["items"][1]["keep"], "y")


if __name__ == "__main__":
    unittest.main()
