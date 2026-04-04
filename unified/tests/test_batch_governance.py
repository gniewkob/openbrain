from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from src import crud, memory_writes
from src.schemas import MemoryWriteManyRequest, MemoryWriteRecord


class BatchGovernanceTests(unittest.IsolatedAsyncioTestCase):
    async def test_handle_memory_write_many_exposes_status_and_previous_record_id(self) -> None:
        session = AsyncMock()
        # Batch lookup returns a result with .all() method returning tuples of (match_key, id)
        session.execute.side_effect = [
            SimpleNamespace(all=lambda: [("mk-versioned", "mem-old-1"), ("mk-created", None)]),
        ]

        records = [
            MemoryWriteRecord(content="versioned", domain="corporate", entity_type="Decision", match_key="mk-versioned"),
            MemoryWriteRecord(content="created", domain="build", entity_type="Note", match_key="mk-created"),
        ]

        responses = [
            SimpleNamespace(
                status="versioned",
                record=SimpleNamespace(id="mem-new-1"),
                warnings=[],
                errors=[],
            ),
            SimpleNamespace(
                status="created",
                record=SimpleNamespace(id="mem-new-2"),
                warnings=[],
                errors=[],
            ),
        ]

        with patch.object(memory_writes, "handle_memory_write", new=AsyncMock(side_effect=responses)):
            result = await memory_writes.handle_memory_write_many(
                session,
                MemoryWriteManyRequest(records=records, write_mode="upsert"),
            )

        self.assertEqual(result.summary["versioned"], 1)
        self.assertEqual(result.summary["created"], 1)
        self.assertEqual(result.results[0].status, "versioned")
        self.assertEqual(result.results[0].previous_record_id, "mem-old-1")
        self.assertEqual(result.results[0].record_id, "mem-new-1")
        self.assertEqual(result.results[1].status, "created")
        self.assertIsNone(result.results[1].previous_record_id)
        self.assertEqual(result.results[1].record_id, "mem-new-2")


if __name__ == "__main__":
    unittest.main()
