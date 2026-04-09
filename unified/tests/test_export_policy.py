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

    async def test_export_redacts_restricted_records_with_strictest_policy(self) -> None:
        session = AsyncMock()
        session.execute.return_value = SimpleNamespace(
            scalars=lambda: SimpleNamespace(all=lambda: [_memory(sensitivity="restricted")])
        )

        result = await export_memories(session, ["mem-1"])

        exported = result[0]
        self.assertEqual(exported["content"], "[REDACTED — restricted sensitivity]")
        self.assertEqual(exported["owner"], "[REDACTED]")
        self.assertEqual(exported["tags"], [])
        self.assertIsNone(exported["match_key"])
        self.assertEqual(exported["custom_fields"], {})
        self.assertEqual(exported["relations"], {})

    async def test_export_falls_back_to_restricted_policy_for_unknown_sensitivity(self) -> None:
        session = AsyncMock()
        session.execute.return_value = SimpleNamespace(
            scalars=lambda: SimpleNamespace(all=lambda: [_memory(sensitivity="super_restricted")])
        )

        result = await export_memories(session, ["mem-1"])

        exported = result[0]
        self.assertEqual(exported["content"], "[REDACTED — super_restricted sensitivity]")
        self.assertEqual(exported["owner"], "[REDACTED]")
        self.assertEqual(exported["tags"], [])
        self.assertIsNone(exported["match_key"])

    async def test_export_keeps_restricted_records_unredacted_for_admin(self) -> None:
        session = AsyncMock()
        session.execute.return_value = SimpleNamespace(
            scalars=lambda: SimpleNamespace(all=lambda: [_memory(sensitivity="restricted")])
        )

        result = await export_memories(session, ["mem-1"], role="admin")

        exported = result[0]
        self.assertEqual(exported["content"], "sensitive payload")
        self.assertEqual(exported["owner"], "owner-a")
        self.assertEqual(exported["match_key"], "mk-1")


if __name__ == "__main__":
    unittest.main()
