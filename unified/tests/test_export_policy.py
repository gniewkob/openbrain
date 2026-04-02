from __future__ import annotations

from datetime import datetime, timezone
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from src.memory_reads import export_memories
from src.models import DomainEnum, Memory


def _memory(**overrides) -> Memory:
    now = datetime.now(timezone.utc)
    payload = {
        "id": "mem-1",
        "domain": DomainEnum.build,
        "entity_type": "Note",
        "content": "sensitive payload",
        "embedding": None,
        "owner": "owner-a",
        "created_by": "tester",
        "status": "active",
        "version": 1,
        "sensitivity": "internal",
        "superseded_by": None,
        "tags": ["alpha"],
        "relations": {"related": ["x"]},
        "metadata_": {"title": "Note", "custom_fields": {"priority": "high"}, "root_id": "mem-1"},
        "obsidian_ref": "notes/openbrain.md",
        "content_hash": "hash-123",
        "match_key": "mk-1",
        "valid_from": None,
        "created_at": now,
        "updated_at": now,
    }
    payload.update(overrides)
    return Memory(**payload)


class ExportPolicyTests(unittest.IsolatedAsyncioTestCase):
    async def test_export_leaves_public_records_unredacted_for_admin(self) -> None:
        session = AsyncMock()
        session.execute.return_value = SimpleNamespace(
            scalars=lambda: SimpleNamespace(all=lambda: [_memory(sensitivity="public")])
        )

        result = await export_memories(session, ["mem-1"], role="admin")

        exported = result[0]
        self.assertEqual(exported["content"], "sensitive payload")
        self.assertEqual(exported["owner"], "owner-a")
        self.assertEqual(exported["custom_fields"], {"priority": "high"})
        self.assertEqual(exported["match_key"], "mk-1")

    async def test_export_redacts_internal_records(self) -> None:
        session = AsyncMock()
        session.execute.return_value = SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: [_memory()]))

        result = await export_memories(session, ["mem-1"])

        self.assertEqual(len(result), 1)
        exported = result[0]
        self.assertEqual(exported["content"], "[REDACTED — internal sensitivity]")
        self.assertEqual(exported["owner"], "[REDACTED]")
        self.assertEqual(exported["relations"], {})
        self.assertEqual(exported["custom_fields"], {})
        self.assertIsNone(exported["obsidian_ref"])
        self.assertEqual(exported["tags"], ["alpha"])
        self.assertEqual(exported["match_key"], "mk-1")

    async def test_export_redacts_confidential_records_more_aggressively(self) -> None:
        session = AsyncMock()
        session.execute.return_value = SimpleNamespace(
            scalars=lambda: SimpleNamespace(all=lambda: [_memory(sensitivity="confidential")])
        )

        result = await export_memories(session, ["mem-1"])

        exported = result[0]
        self.assertEqual(exported["content"], "[REDACTED — confidential sensitivity]")
        self.assertEqual(exported["tags"], [])
        self.assertIsNone(exported["match_key"])
        self.assertEqual(exported["custom_fields"], {})

    async def test_export_redacts_internal_records_for_internal_role(self) -> None:
        session = AsyncMock()
        session.execute.return_value = SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: [_memory()]))

        result = await export_memories(session, ["mem-1"], role="internal")

        exported = result[0]
        self.assertEqual(exported["content"], "[REDACTED — internal sensitivity]")
        self.assertEqual(exported["owner"], "[REDACTED]")
        self.assertEqual(exported["tags"], [])


if __name__ == "__main__":
    unittest.main()
