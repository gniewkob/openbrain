"""Tests for memory use-case wrappers."""

from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from src.schemas import (
    MaintenanceRequest,
    MemoryFindRequest,
    MemoryGetContextRequest,
    MemoryUpsertItem,
    MemoryUpdate,
    MemoryWriteManyRequest,
    MemoryWriteRecord,
    MemoryWriteRequest,
)
from src.use_cases import memory as memory_use_cases


class MemoryUseCaseTests(unittest.IsolatedAsyncioTestCase):
    async def test_store_memory_delegates_to_write_engine(self) -> None:
        request = MemoryWriteRequest(
            record=MemoryWriteRecord(
                content="payload",
                domain="build",
                entity_type="Note",
            ),
            write_mode="upsert",
        )
        session = AsyncMock()
        expected = {"status": "created"}

        with patch.object(
            memory_use_cases,
            "handle_memory_write",
            new=AsyncMock(return_value=expected),
        ) as mocked:
            result = await memory_use_cases.store_memory(
                session,
                request,
                actor="agent-1",
            )

        self.assertEqual(result, expected)
        mocked.assert_awaited_once_with(session, request, actor="agent-1")

    async def test_update_memory_delegates_to_write_path(self) -> None:
        session = AsyncMock()
        payload = MemoryUpdate(content="after")
        expected = {"id": "mem-1"}

        with patch.object(
            memory_use_cases,
            "update_memory_write",
            new=AsyncMock(return_value=expected),
        ) as mocked:
            result = await memory_use_cases.update_memory(
                session,
                "mem-1",
                payload,
                actor="agent-2",
            )

        self.assertEqual(result, expected)
        mocked.assert_awaited_once_with(session, "mem-1", payload, actor="agent-2")

    async def test_store_memories_many_delegates_to_write_engine(self) -> None:
        request = MemoryWriteManyRequest(
            records=[
                MemoryWriteRecord(
                    content="bulk payload",
                    domain="build",
                    entity_type="Note",
                )
            ],
            write_mode="upsert",
        )
        session = AsyncMock()
        expected = {"summary": {"created": 1}}

        with patch.object(
            memory_use_cases,
            "handle_memory_write_many",
            new=AsyncMock(return_value=expected),
        ) as mocked:
            result = await memory_use_cases.store_memories_many(
                session,
                request,
                actor="agent-bulk",
            )

        self.assertEqual(result, expected)
        mocked.assert_awaited_once_with(session, request, actor="agent-bulk")

    async def test_delete_memory_delegates_to_write_path(self) -> None:
        session = AsyncMock()
        with patch.object(
            memory_use_cases,
            "delete_memory_write",
            new=AsyncMock(return_value=True),
        ) as mocked:
            result = await memory_use_cases.delete_memory(
                session,
                "mem-9",
                actor="agent-3",
            )

        self.assertTrue(result)
        mocked.assert_awaited_once_with(session, "mem-9", actor="agent-3")

    async def test_run_maintenance_delegates_to_write_path(self) -> None:
        session = AsyncMock()
        req = MaintenanceRequest(dry_run=True)
        expected = {"run_id": "maint-1"}

        with patch.object(
            memory_use_cases,
            "run_maintenance_write",
            new=AsyncMock(return_value=expected),
        ) as mocked:
            result = await memory_use_cases.run_maintenance(
                session,
                req,
                actor="admin-1",
            )

        self.assertEqual(result, expected)
        mocked.assert_awaited_once_with(session, req, actor="admin-1")

    async def test_upsert_memories_bulk_delegates_to_write_path(self) -> None:
        session = AsyncMock()
        items = [
            MemoryUpsertItem(
                content="bulk upsert",
                domain="build",
                entity_type="Note",
                match_key="mk-1",
            )
        ]
        expected = {"inserted": [], "updated": [], "skipped": []}

        with patch.object(
            memory_use_cases,
            "upsert_memories_bulk_write",
            new=AsyncMock(return_value=expected),
        ) as mocked:
            result = await memory_use_cases.upsert_memories_bulk(session, items)

        self.assertEqual(result, expected)
        mocked.assert_awaited_once_with(session, items)

    async def test_search_memories_delegates_to_v1_find(self) -> None:
        session = AsyncMock()
        req = MemoryFindRequest(query="security", limit=5, filters={})
        expected = [({"id": "mem-1"}, 0.88)]

        with patch.object(
            memory_use_cases,
            "find_memories_v1",
            new=AsyncMock(return_value=expected),
        ) as mocked:
            result = await memory_use_cases.search_memories(session, req)

        self.assertEqual(result, expected)
        mocked.assert_awaited_once_with(session, req)

    async def test_get_memory_context_delegates_to_grounding_pack(self) -> None:
        session = AsyncMock()
        req = MemoryGetContextRequest(query="runbook")
        expected = {"summary": "ok"}

        with patch.object(
            memory_use_cases,
            "get_grounding_pack",
            new=AsyncMock(return_value=expected),
        ) as mocked:
            result = await memory_use_cases.get_memory_context(
                session,
                req,
                owner="owner-a",
                tenant_id="tenant-a",
            )

        self.assertEqual(result, expected)
        mocked.assert_awaited_once_with(
            session,
            req,
            owner="owner-a",
            tenant_id="tenant-a",
        )


if __name__ == "__main__":
    unittest.main()
