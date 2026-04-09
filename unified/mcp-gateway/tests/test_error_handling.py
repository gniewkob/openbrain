"""Tests for _raise() — production vs dev error message format."""

from __future__ import annotations

import asyncio
import os
import unittest

import httpx

from helpers import load_gateway_main


class RaiseProductionModeTests(unittest.TestCase):
    """In production mode, errors include HTTP status code but hide body details."""

    def setUp(self) -> None:
        os.environ["ENV"] = "production"

    def tearDown(self) -> None:
        os.environ.pop("ENV", None)

    def _make_response(self, status: int) -> httpx.Response:
        return httpx.Response(
            status,
            json={"detail": "sensitive internal info"},
            request=httpx.Request("GET", "http://backend/api/v1/memory/x"),
        )

    def _call_raise(self, status: int) -> str:
        gateway = load_gateway_main()

        with self.assertRaises(ValueError) as ctx:
            gateway._raise(self._make_response(status))
        return str(ctx.exception)

    def test_500_includes_status_code(self) -> None:
        msg = self._call_raise(500)
        self.assertIn("500", msg)

    def test_500_hides_body(self) -> None:
        msg = self._call_raise(500)
        self.assertNotIn("sensitive internal info", msg)

    def test_404_includes_status_code(self) -> None:
        msg = self._call_raise(404)
        self.assertIn("404", msg)

    def test_401_includes_status_code(self) -> None:
        msg = self._call_raise(401)
        self.assertIn("401", msg)

    def test_403_includes_status_code(self) -> None:
        msg = self._call_raise(403)
        self.assertIn("403", msg)

    def test_422_includes_status_code(self) -> None:
        msg = self._call_raise(422)
        self.assertIn("422", msg)

    def test_200_does_not_raise(self) -> None:
        gateway = load_gateway_main()

        response = httpx.Response(
            200,
            json={"id": "mem_1"},
            request=httpx.Request("GET", "http://backend/api/v1/memory/x"),
        )
        gateway._raise(response)  # must not raise

    def test_request_error_in_production_is_masked(self) -> None:
        gateway = load_gateway_main()
        with self.assertRaises(ValueError) as ctx:
            asyncio.run(
                gateway._request_or_raise(
                    _FailingClient(),
                    "GET",
                    "http://backend/api/v1/memory/x",
                )
            )

        msg = str(ctx.exception)
        self.assertIn("Backend request failed", msg)
        self.assertNotIn("connect timeout", msg)


class RaiseDevelopmentModeTests(unittest.TestCase):
    """In dev mode, errors include the actual response body for debugging."""

    def setUp(self) -> None:
        os.environ.pop("ENV", None)

    def test_dev_mode_includes_body(self) -> None:
        gateway = load_gateway_main()

        response = httpx.Response(
            500,
            json={"detail": "NullPointerException in memory_writes.py:42"},
            request=httpx.Request("GET", "http://backend/api/v1/memory/x"),
        )
        with self.assertRaises(ValueError) as ctx:
            gateway._raise(response)

        msg = str(ctx.exception)
        self.assertIn("500", msg)
        self.assertIn("NullPointerException", msg)

    def test_dev_mode_non_json_body(self) -> None:
        gateway = load_gateway_main()

        response = httpx.Response(
            503,
            content=b"Service Unavailable",
            request=httpx.Request("GET", "http://backend/api/v1/memory/x"),
        )
        with self.assertRaises(ValueError) as ctx:
            gateway._raise(response)

        msg = str(ctx.exception)
        self.assertIn("503", msg)
        self.assertIn("Service Unavailable", msg)

    def test_request_error_in_dev_includes_detail(self) -> None:
        gateway = load_gateway_main()
        with self.assertRaises(ValueError) as ctx:
            asyncio.run(
                gateway._request_or_raise(
                    _FailingClient(),
                    "GET",
                    "http://backend/api/v1/memory/x",
                )
            )

        msg = str(ctx.exception)
        self.assertIn("Backend request failed", msg)
        self.assertIn("connect timeout", msg)


class _FailingClient:
    async def request(self, method: str, path: str, **kwargs):
        raise httpx.ConnectError(
            "connect timeout",
            request=httpx.Request(method, path),
        )
