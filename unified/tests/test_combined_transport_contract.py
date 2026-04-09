from __future__ import annotations

import unittest

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


if __name__ == "__main__":
    unittest.main()
