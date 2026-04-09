from __future__ import annotations

import unittest
from unittest.mock import patch

from src import combined, mcp_transport


class CombinedTransportContractTests(unittest.IsolatedAsyncioTestCase):
    async def test_root_redirect_uses_streamable_http_path_constant(self) -> None:
        events: list[dict] = []

        async def _receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def _send(event: dict) -> None:
            events.append(event)

        scope = {
            "type": "http",
            "path": "/",
            "method": "GET",
            "headers": [],
            "query_string": b"",
            "scheme": "http",
            "http_version": "1.1",
            "server": ("test", 80),
            "client": ("test", 12345),
        }

        await combined.app(scope, _receive, _send)

        self.assertGreaterEqual(len(events), 2)
        self.assertEqual(events[0]["type"], "http.response.start")
        self.assertEqual(events[0]["status"], 307)
        headers = dict(events[0]["headers"])
        self.assertEqual(
            headers.get(b"location"),
            mcp_transport.STREAMABLE_HTTP_PATH.encode("ascii"),
        )

    async def test_root_redirect_returns_503_for_invalid_root_transport_path(
        self,
    ) -> None:
        events: list[dict] = []

        async def _receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def _send(event: dict) -> None:
            events.append(event)

        scope = {
            "type": "http",
            "path": "/",
            "method": "GET",
            "headers": [],
            "query_string": b"",
            "scheme": "http",
            "http_version": "1.1",
            "server": ("test", 80),
            "client": ("test", 12345),
        }

        with patch.object(mcp_transport, "STREAMABLE_HTTP_PATH", "/"):
            await combined.app(scope, _receive, _send)

        self.assertGreaterEqual(len(events), 2)
        self.assertEqual(events[0]["type"], "http.response.start")
        self.assertEqual(events[0]["status"], 503)
        headers = dict(events[0]["headers"])
        self.assertEqual(headers.get(b"content-type"), b"application/json")
        self.assertEqual(
            events[1]["body"],
            b'{"detail":"Invalid MCP streamable transport path configuration"}',
        )

    async def test_root_redirect_reads_streamable_path_from_transport_module(
        self,
    ) -> None:
        events: list[dict] = []

        async def _receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def _send(event: dict) -> None:
            events.append(event)

        scope = {
            "type": "http",
            "path": "/",
            "method": "GET",
            "headers": [],
            "query_string": b"",
            "scheme": "http",
            "http_version": "1.1",
            "server": ("test", 80),
            "client": ("test", 12345),
        }

        with patch.object(mcp_transport, "STREAMABLE_HTTP_PATH", "/events"):
            await combined.app(scope, _receive, _send)

        self.assertGreaterEqual(len(events), 2)
        self.assertEqual(events[0]["type"], "http.response.start")
        self.assertEqual(events[0]["status"], 307)
        headers = dict(events[0]["headers"])
        self.assertEqual(headers.get(b"location"), b"/events")


if __name__ == "__main__":
    unittest.main()
