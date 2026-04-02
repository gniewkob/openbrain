from __future__ import annotations

import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

from src.memory_reads import sync_check
from src.models import DomainEnum, Memory


def _memory(**overrides) -> Memory:
    now = datetime.now(timezone.utc)
    payload = {
        "id": "mem-1",
        "domain": DomainEnum.build,
        "entity_type": "Note",
        "content": "payload",
        "embedding": None,
        "owner": "owner-a",
        "created_by": "tester",
        "status": "active",
        "version": 1,
        "sensitivity": "internal",
        "superseded_by": None,
        "tags": ["sync"],
        "relations": {},
        "metadata_": {"title": "Note"},
        "obsidian_ref": "notes/openbrain.md",
        "content_hash": "hash-123",
        "match_key": "mk-1",
        "valid_from": None,
        "created_at": now,
        "updated_at": now,
    }
    payload.update(overrides)
    return Memory(**payload)


class SyncCheckTests(unittest.IsolatedAsyncioTestCase):
    async def test_sync_check_returns_missing_for_unknown_identifier(self) -> None:
        session = AsyncMock()
        session.execute.return_value = SimpleNamespace(scalar_one_or_none=lambda: None)

        result = await sync_check(session, match_key="missing")

        self.assertEqual(result["status"], "missing")
        self.assertEqual(result["match_key"], "missing")
        self.assertIsNone(result["stored_hash"])

    async def test_sync_check_returns_exists_without_file_hash(self) -> None:
        session = AsyncMock()
        session.execute.return_value = SimpleNamespace(scalar_one_or_none=lambda: _memory())

        result = await sync_check(session, memory_id="mem-1")

        self.assertEqual(result["status"], "exists")
        self.assertEqual(result["memory_id"], "mem-1")
        self.assertEqual(result["stored_hash"], "hash-123")
        self.assertIsNone(result["provided_hash"])

    async def test_sync_check_returns_synced_for_matching_hash(self) -> None:
        session = AsyncMock()
        session.execute.return_value = SimpleNamespace(scalar_one_or_none=lambda: _memory())

        result = await sync_check(session, obsidian_ref="notes/openbrain.md", file_hash="hash-123")

        self.assertEqual(result["status"], "synced")
        self.assertEqual(result["provided_hash"], "hash-123")

    async def test_sync_check_returns_outdated_for_hash_mismatch(self) -> None:
        session = AsyncMock()
        session.execute.return_value = SimpleNamespace(scalar_one_or_none=lambda: _memory())

        result = await sync_check(session, match_key="mk-1", file_hash="hash-999")

        self.assertEqual(result["status"], "outdated")
        self.assertEqual(result["stored_hash"], "hash-123")
        self.assertEqual(result["provided_hash"], "hash-999")


if __name__ == "__main__":
    unittest.main()
