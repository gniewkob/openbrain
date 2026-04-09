from __future__ import annotations

import unittest

from helpers import load_gateway_module


mcp_http = load_gateway_module("mcp_http")


class McpHttpConfigTests(unittest.TestCase):
    def test_normalize_public_base_url_trims_and_drops_trailing_slash(self) -> None:
        self.assertEqual(
            mcp_http._normalize_public_base_url("  https://example.com/  "),
            "https://example.com",
        )

    def test_normalize_public_base_url_rejects_whitespace(self) -> None:
        with self.assertRaisesRegex(ValueError, "PUBLIC_BASE_URL"):
            mcp_http._normalize_public_base_url("https://exa mple.com")

    def test_normalize_public_base_url_rejects_path(self) -> None:
        with self.assertRaisesRegex(ValueError, "PUBLIC_BASE_URL"):
            mcp_http._normalize_public_base_url("https://example.com/mcp")

    def test_normalize_public_base_url_rejects_query(self) -> None:
        with self.assertRaisesRegex(ValueError, "PUBLIC_BASE_URL"):
            mcp_http._normalize_public_base_url("https://example.com?x=1")

    def test_normalize_public_base_url_rejects_http_non_localhost(self) -> None:
        with self.assertRaisesRegex(ValueError, "PUBLIC_BASE_URL"):
            mcp_http._normalize_public_base_url("http://example.com")

    def test_normalize_public_base_url_allows_http_localhost(self) -> None:
        self.assertEqual(
            mcp_http._normalize_public_base_url("http://localhost:7011"),
            "http://localhost:7011",
        )

    def test_normalize_mcp_http_port_accepts_valid_port(self) -> None:
        self.assertEqual(mcp_http._normalize_mcp_http_port("7011"), 7011)

    def test_normalize_mcp_http_port_rejects_non_integer(self) -> None:
        with self.assertRaisesRegex(ValueError, "MCP_HTTP_PORT"):
            mcp_http._normalize_mcp_http_port("abc")

    def test_normalize_mcp_http_port_rejects_out_of_range(self) -> None:
        with self.assertRaisesRegex(ValueError, "MCP_HTTP_PORT"):
            mcp_http._normalize_mcp_http_port("70000")
