from __future__ import annotations

from datetime import datetime, timezone
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from src import crud, memory_reads, memory_writes
from src.models import DomainEnum, Memory
from src.schemas import (
    MemoryFindRequest,
    MemoryWriteRecord,
    MemoryWriteRequest,
    SearchRequest,
    WriteMode,
)


class SearchPolicyTests(unittest.IsolatedAsyncioTestCase):
    async def test_search_memories_applies_owner_filter(self) -> None:
        captured_stmt = None

        async def execute(stmt):
            nonlocal captured_stmt
            captured_stmt = stmt
            return SimpleNamespace(all=lambda: [])

        session = SimpleNamespace(execute=execute)

        with patch.object(
            memory_reads,
            "_get_embedding_compat",
            new=AsyncMock(return_value=[0.1, 0.2, 0.3]),
        ):
            await memory_reads.search_memories(
                session,
                SearchRequest(query="policy", top_k=5, filters={"owner": "owner-a"}),
            )

        self.assertIsNotNone(captured_stmt)
        stmt_text = str(captured_stmt)
        self.assertIn("memories.owner", stmt_text)

    async def test_search_memories_filters_to_active_records_only(self) -> None:
        captured_stmt = None

        async def execute(stmt):
            nonlocal captured_stmt
            captured_stmt = stmt
            return SimpleNamespace(all=lambda: [])

        session = SimpleNamespace(execute=execute)

        with patch.object(
            memory_reads,
            "_get_embedding_compat",
            new=AsyncMock(return_value=[0.1, 0.2, 0.3]),
        ):
            result = await memory_reads.search_memories(
                session, SearchRequest(query="policy", top_k=5)
            )

        self.assertEqual(result, [])
        self.assertIsNotNone(captured_stmt)
        stmt_text = str(captured_stmt)
        self.assertIn("memories.status", stmt_text)
        self.assertIn("= :status_1", stmt_text)

    async def test_search_memories_never_returns_superseded_even_with_status_filter(
        self,
    ) -> None:
        captured_stmt = None

        async def execute(stmt):
            nonlocal captured_stmt
            captured_stmt = stmt
            return SimpleNamespace(all=lambda: [])

        session = SimpleNamespace(execute=execute)

        with patch.object(
            memory_reads,
            "_get_embedding_compat",
            new=AsyncMock(return_value=[0.1, 0.2, 0.3]),
        ):
            result = await memory_reads.search_memories(
                session,
                SearchRequest(
                    query="policy",
                    top_k=5,
                    filters={"status": "superseded"},
                ),
            )

        self.assertEqual(result, [])
        self.assertIsNotNone(captured_stmt)
        stmt_text = str(captured_stmt)
        # Invariant guard: semantic search always enforces active records only.
        self.assertGreaterEqual(stmt_text.count("memories.status"), 2)

    async def test_find_memories_v1_filters_to_active_records_only(self) -> None:
        captured_stmt = None

        async def execute(stmt):
            nonlocal captured_stmt
            captured_stmt = stmt
            return SimpleNamespace(all=lambda: [])

        session = SimpleNamespace(execute=execute)

        with patch.object(
            memory_reads,
            "_get_embedding_compat",
            new=AsyncMock(return_value=[0.1, 0.2, 0.3]),
        ):
            result = await memory_reads.find_memories_v1(
                session, MemoryFindRequest(query="policy", limit=5)
            )

        self.assertEqual(result, [])
        self.assertIsNotNone(captured_stmt)
        stmt_text = str(captured_stmt)
        self.assertIn("memories.status", stmt_text)
        self.assertIn("= :status_1", stmt_text)

    async def test_append_version_marks_previous_record_as_superseded(self) -> None:
        now = datetime.now(timezone.utc)
        existing = Memory(
            id="mem-1",
            domain=DomainEnum.corporate,
            entity_type="Decision",
            content="before",
            embedding=[0.1, 0.2],
            owner="owner-a",
            created_by="tester",
            status="active",
            version=1,
            sensitivity="internal",
            superseded_by=None,
            tags=["alpha"],
            relations={},
            metadata_={"title": "Decision", "root_id": "mem-1"},
            obsidian_ref=None,
            content_hash="hash-before",
            match_key="corp:decision:1",
            valid_from=None,
            created_at=now,
            updated_at=now,
        )

        session = AsyncMock()
        session.execute.return_value = SimpleNamespace(
            scalar_one_or_none=lambda: existing
        )
        session.commit = AsyncMock()
        session.refresh = AsyncMock()
        added: list[object] = []
        session.add = lambda obj: added.append(obj)

        async def _flush() -> None:
            now_inner = datetime.now(timezone.utc)
            for idx, obj in enumerate(added, start=2):
                if not getattr(obj, "id", None):
                    obj.id = f"mem-{idx}"
                if not getattr(obj, "created_at", None):
                    obj.created_at = now_inner
                if not getattr(obj, "updated_at", None):
                    obj.updated_at = now_inner

        session.flush = AsyncMock(side_effect=_flush)

        with patch.object(
            memory_writes,
            "_get_embedding_compat",
            new=AsyncMock(return_value=[0.3, 0.4]),
        ):
            result = await memory_writes.handle_memory_write(
                session,
                MemoryWriteRequest(
                    record=MemoryWriteRecord(
                        content="after",
                        domain="corporate",
                        entity_type="Decision",
                        owner="owner-a",
                        match_key="corp:decision:1",
                    ),
                    write_mode=WriteMode.append_version,
                ),
            )

        self.assertEqual(result.status, "versioned")
        self.assertEqual(existing.status, "superseded")
        self.assertEqual(existing.superseded_by, result.record.id)


if __name__ == "__main__":
    unittest.main()
