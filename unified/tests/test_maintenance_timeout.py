"""Test that run_maintenance respects MAINTENANCE_TIMEOUT_S."""

from __future__ import annotations

import asyncio
import unittest
from unittest.mock import AsyncMock, patch


class MaintenanceTimeoutTests(unittest.IsolatedAsyncioTestCase):
    async def test_run_maintenance_respects_timeout(self) -> None:
        """run_maintenance must raise TimeoutError when MAINTENANCE_TIMEOUT_S is exceeded."""
        from src.schemas import MaintenanceRequest

        req = MaintenanceRequest(dedup_threshold=0.95, dry_run=True)

        # session.execute hangs forever — simulates a slow DB
        session = AsyncMock()

        async def _hang(*_args, **_kwargs):
            await asyncio.sleep(9999)

        session.execute.side_effect = _hang

        with patch.dict("os.environ", {"MAINTENANCE_TIMEOUT_S": "0.05"}):
            from src import memory_writes

            with self.assertRaises((asyncio.TimeoutError, TimeoutError)):
                await memory_writes.run_maintenance(session, req, actor="test")

    async def test_run_maintenance_succeeds_within_timeout(self) -> None:
        """run_maintenance must NOT raise when it completes before the timeout."""
        from src import memory_writes
        from src.schemas import MaintenanceRequest

        req = MaintenanceRequest(dedup_threshold=0.0, dry_run=True)

        # Minimal session mock that returns sensible values immediately
        session = AsyncMock()
        count_result = AsyncMock()
        count_result.scalar_one.return_value = 0
        session.execute.return_value = count_result
        session.flush = AsyncMock()
        session.commit = AsyncMock()

        # Patch _run_maintenance_inner's audit log creation to avoid schema issues
        with patch.object(
            memory_writes, "_run_maintenance_inner", new=AsyncMock(return_value=None)
        ):
            with patch.dict("os.environ", {"MAINTENANCE_TIMEOUT_S": "10"}):
                # Should not raise — returns None from mock
                result = await memory_writes.run_maintenance(session, req, actor="test")
                assert result is None  # mocked inner returns None


if __name__ == "__main__":
    unittest.main()
