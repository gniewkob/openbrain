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

    def test_extract_record_from_write_response_success(self) -> None:
        """Test successful path for extracting and normalizing record."""
        payload = {"record": {"key": "val"}}
        result = utils.extract_record_from_write_response(
            payload, lambda x: {**x, "legacy": True}
        )
        self.assertEqual(result, {"key": "val", "legacy": True})

    def test_http_obsidian_disabled_reason(self) -> None:
        """Test standard disabled reason for HTTP Obsidian tool surface."""
        reason = utils.http_obsidian_disabled_reason()
        self.assertIn("HTTP Obsidian tools are disabled by default", reason)

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

    def test_redact_logged_payload_scalars(self) -> None:
        """Test that scalar values are returned completely unchanged."""
        sensitive = {"secret", "password"}
        self.assertEqual(utils.redact_logged_payload(None, sensitive), None)
        self.assertEqual(utils.redact_logged_payload("hello", sensitive), "hello")
        self.assertEqual(utils.redact_logged_payload(12345, sensitive), 12345)
        self.assertEqual(utils.redact_logged_payload(3.14159, sensitive), 3.14159)
        self.assertEqual(utils.redact_logged_payload(True, sensitive), True)

    def test_redact_logged_payload_empty_and_unused_sensitive(self) -> None:
        """Test with empty structures and/or empty sensitive fields."""
        payload = {"key": "value", "sublist": []}
        # No sensitive fields
        self.assertEqual(utils.redact_logged_payload(payload, set()), payload)
        # Empty dict payload
        self.assertEqual(utils.redact_logged_payload({}, {"secret"}), {})
        # Empty list payload
        self.assertEqual(utils.redact_logged_payload([], {"secret"}), [])

    def test_redact_logged_payload_non_mutation(self) -> None:
        """Test that the original input payload structure is not modified in-place."""
        payload = {
            "secret": "original_secret",
            "nested": {"secret": "inner_secret", "normal": "value"},
            "items": [{"secret": "item_secret"}, "normal_string"],
        }
        sensitive = {"secret"}
        redacted = utils.redact_logged_payload(payload, sensitive)

        # Verify redaction succeeded
        self.assertEqual(redacted["secret"], "[REDACTED]")
        self.assertEqual(redacted["nested"]["secret"], "[REDACTED]")
        self.assertEqual(redacted["items"][0]["secret"], "[REDACTED]")

        # Verify original was NOT mutated
        self.assertEqual(payload["secret"], "original_secret")
        self.assertEqual(payload["nested"]["secret"], "inner_secret")
        self.assertEqual(payload["items"][0]["secret"], "item_secret")

    def test_redact_logged_payload_complex_nesting(self) -> None:
        """Test deep and complex nesting of lists of lists, dicts, and mixed structures."""
        payload = {
            "matrix": [
                [{"secret": "nested1"}, {"keep": "keep1"}],
                [{"secret": "nested2"}, {"keep": "keep2"}],
            ],
            "deep": {
                "level1": {
                    "level2": {
                        "secret": "very_deep",
                        "values": ["a", "b", {"secret": "inner"}],
                    }
                }
            },
        }
        sensitive = {"secret"}
        redacted = utils.redact_logged_payload(payload, sensitive)

        expected = {
            "matrix": [
                [{"secret": "[REDACTED]"}, {"keep": "keep1"}],
                [{"secret": "[REDACTED]"}, {"keep": "keep2"}],
            ],
            "deep": {
                "level1": {
                    "level2": {
                        "secret": "[REDACTED]",
                        "values": ["a", "b", {"secret": "[REDACTED]"}],
                    }
                }
            },
        }
        self.assertEqual(redacted, expected)

    def test_redact_logged_payload_unsupported_iterables(self) -> None:
        """Test that other types like tuples and sets are returned unchanged and not crashed."""
        sensitive = {"secret"}
        tup = ("keep", "secret")
        self.assertEqual(utils.redact_logged_payload(tup, sensitive), tup)

        # A dict containing a tuple or set
        payload = {
            "tuple_field": ("secret", "keep"),
            "set_field": {"secret", "keep"},
            "secret": "yes",
        }
        redacted = utils.redact_logged_payload(payload, sensitive)
        self.assertEqual(redacted["tuple_field"], ("secret", "keep"))
        self.assertEqual(redacted["set_field"], {"secret", "keep"})
        self.assertEqual(redacted["secret"], "[REDACTED]")

    def test_redact_logged_payload_case_sensitivity(self) -> None:
        """Test that sensitive fields are case-sensitive."""
        payload = {
            "SECRET": "not redacted",
            "secret": "redacted",
            "Secret": "not redacted",
        }
        sensitive = {"secret"}
        redacted = utils.redact_logged_payload(payload, sensitive)
        self.assertEqual(redacted["SECRET"], "not redacted")
        self.assertEqual(redacted["secret"], "[REDACTED]")
        self.assertEqual(redacted["Secret"], "not redacted")


if __name__ == "__main__":
    unittest.main()
