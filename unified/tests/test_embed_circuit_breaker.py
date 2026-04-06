"""Tests for Ollama embedding circuit breaker."""

from __future__ import annotations

import asyncio
import unittest
from unittest.mock import patch
import httpx


class CircuitBreakerStateTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        from src.embed import _circuit_breaker

        _circuit_breaker.reset()

    async def test_initial_state_is_closed(self) -> None:
        from src.embed import _circuit_breaker

        self.assertEqual(_circuit_breaker.state, "closed")

    async def test_guard_passes_when_closed(self) -> None:
        from src.embed import _circuit_breaker

        # Must not raise
        await _circuit_breaker.guard()

    async def test_failures_trip_circuit(self) -> None:
        from src.embed import _circuit_breaker

        for _ in range(3):
            _circuit_breaker.on_failure()
        self.assertEqual(_circuit_breaker.state, "open")

    async def test_circuit_open_raises_immediately(self) -> None:
        import time
        from src.embed import _circuit_breaker, CircuitOpenError

        _circuit_breaker._state = "open"
        _circuit_breaker._opened_at = time.monotonic()  # just opened
        with self.assertRaises(CircuitOpenError):
            await _circuit_breaker.guard()

    async def test_circuit_transitions_to_half_open_after_timeout(self) -> None:
        from src.embed import _circuit_breaker

        _circuit_breaker._state = "open"
        _circuit_breaker._opened_at = 0.0  # opened long ago
        # guard should NOT raise — should transition to half_open
        await _circuit_breaker.guard()
        self.assertEqual(_circuit_breaker.state, "half_open")

    async def test_success_closes_circuit(self) -> None:
        from src.embed import _circuit_breaker

        _circuit_breaker._state = "half_open"
        _circuit_breaker.on_success()
        self.assertEqual(_circuit_breaker.state, "closed")
        self.assertEqual(_circuit_breaker._failures, 0)

    async def test_failure_in_half_open_reopens_circuit(self) -> None:
        from src.embed import _circuit_breaker

        _circuit_breaker._state = "half_open"
        _circuit_breaker._failures = 2
        _circuit_breaker.on_failure()
        self.assertEqual(_circuit_breaker.state, "open")


class CircuitBreakerGetEmbeddingTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        from src.embed import _circuit_breaker

        _circuit_breaker.reset()

    async def test_connect_error_trips_circuit_after_threshold(self) -> None:
        from src.embed import _circuit_breaker, get_embedding

        call_count = 0

        async def _failing_post(path, payload):
            nonlocal call_count
            call_count += 1
            raise httpx.ConnectError("Connection refused")

        with patch("src.embed._post_with_retry", side_effect=_failing_post):
            for _ in range(3):
                with self.assertRaises(httpx.ConnectError):
                    await get_embedding("test")

        self.assertEqual(_circuit_breaker.state, "open")

    async def test_circuit_open_raises_circuit_open_error(self) -> None:
        import time
        from src.embed import _circuit_breaker, get_embedding, CircuitOpenError

        _circuit_breaker._state = "open"
        _circuit_breaker._opened_at = time.monotonic()  # just tripped

        with self.assertRaises(CircuitOpenError):
            await get_embedding("test")

    async def test_successful_call_closes_circuit(self) -> None:
        from src.embed import _circuit_breaker, get_embedding

        # Set circuit to half_open so one probe is allowed
        _circuit_breaker._state = "half_open"

        fake_response = unittest.mock.MagicMock()
        fake_response.status_code = 200
        fake_response.json.return_value = {"embeddings": [[0.1, 0.2, 0.3]]}

        with patch("src.embed._post_with_retry", return_value=fake_response):
            result = await get_embedding("hello")

        self.assertEqual(_circuit_breaker.state, "closed")
        self.assertEqual(result, [0.1, 0.2, 0.3])


if __name__ == "__main__":
    unittest.main()
