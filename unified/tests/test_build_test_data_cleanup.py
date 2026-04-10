from __future__ import annotations

from datetime import datetime, timezone
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from src import memory_writes


class BuildTestDataCleanupWriteTests(unittest.IsolatedAsyncioTestCase):
    async def test_cleanup_build_test_data_dry_run_returns_candidates_only(self) -> None:
        now = datetime.now(timezone.utc)
        session = AsyncMock()
        session.execute = AsyncMock(
            return_value=SimpleNamespace(
                all=lambda: [
                    SimpleNamespace(id="mem-1", updated_at=now),
                    SimpleNamespace(id="mem-2", updated_at=now),
                ]
            )
        )

        with patch.object(memory_writes, "delete_memory", new=AsyncMock()) as delete_mock:
            result = await memory_writes.cleanup_build_test_data(
                session,
                dry_run=True,
                limit=10,
                actor="tester",
            )

        self.assertTrue(result.dry_run)
        self.assertEqual(result.candidates_count, 2)
        self.assertEqual(result.deleted_count, 0)
        self.assertEqual(result.candidate_ids, ["mem-1", "mem-2"])
        delete_mock.assert_not_called()

    async def test_cleanup_build_test_data_executes_delete_and_collects_skips(self) -> None:
        now = datetime.now(timezone.utc)
        session = AsyncMock()
        session.execute = AsyncMock(
            return_value=SimpleNamespace(
                all=lambda: [
                    SimpleNamespace(id="mem-1", updated_at=now),
                    SimpleNamespace(id="mem-2", updated_at=now),
                ]
            )
        )

        with patch.object(
            memory_writes,
            "delete_memory",
            new=AsyncMock(side_effect=[True, ValueError("Cannot hard-delete append-only memories.")]),
        ):
            result = await memory_writes.cleanup_build_test_data(
                session,
                dry_run=False,
                limit=10,
                actor="tester",
            )

        self.assertFalse(result.dry_run)
        self.assertEqual(result.candidates_count, 2)
        self.assertEqual(result.deleted_count, 1)
        self.assertEqual(result.skipped_count, 1)
        self.assertEqual(result.deleted_ids, ["mem-1"])
        self.assertEqual(result.skipped[0].id, "mem-2")


class BuildTestDataCleanupEndpointTests(unittest.IsolatedAsyncioTestCase):
    async def test_endpoint_requires_admin(self) -> None:
        from src.api.v1 import memory as mem_module

        request = mem_module.BuildTestDataCleanupRequest(dry_run=True, limit=5)

        with patch.object(
            mem_module,
            "require_admin",
            side_effect=HTTPException(status_code=403, detail="Admin privileges required"),
        ):
            with self.assertRaises(HTTPException) as ctx:
                await mem_module.cleanup_build_test_data(
                    req=request,
                    session=object(),
                    _user={"sub": "non-admin"},
                )
        self.assertEqual(ctx.exception.status_code, 403)

    async def test_endpoint_calls_use_case(self) -> None:
        from src.api.v1 import memory as mem_module

        request = mem_module.BuildTestDataCleanupRequest(dry_run=False, limit=5)
        fake_response = mem_module.BuildTestDataCleanupResponse(
            dry_run=False,
            scanned=2,
            candidates_count=2,
            deleted_count=2,
            skipped_count=0,
            candidate_ids=["mem-1", "mem-2"],
            deleted_ids=["mem-1", "mem-2"],
            skipped=[],
        )

        with (
            patch.object(mem_module, "require_admin"),
            patch.object(
                mem_module,
                "cleanup_build_test_data_use_case",
                new=AsyncMock(return_value=fake_response),
            ) as use_case_mock,
        ):
            result = await mem_module.cleanup_build_test_data(
                req=request,
                session=object(),
                _user={"sub": "admin-user"},
            )

        self.assertEqual(result.deleted_count, 2)
        use_case_mock.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
