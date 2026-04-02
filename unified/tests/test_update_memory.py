from __future__ import annotations

import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from src import crud, memory_writes
from src.crud_common import _to_out, _to_record
from src.models import DomainEnum, Memory
from src.schemas import (
    MemoryOut,
    MemoryRecord,
    MemoryRelations,
    MemoryUpdate,
    MemoryWriteResponse,
    SourceMetadata,
    GovernanceMetadata,
)


class UpdateMemoryTests(unittest.IsolatedAsyncioTestCase):
    async def test_update_memory_preserves_match_key_and_existing_metadata(self) -> None:
        now = datetime.now(timezone.utc)
        existing = Memory(
            id="mem-1",
            domain=DomainEnum.build,
            entity_type="Architecture",
            content="before",
            embedding=None,
            owner="owner-a",
            created_by="tester",
            status="active",
            version=1,
            sensitivity="internal",
            superseded_by=None,
            tags=["alpha"],
            relations={"related": ["x"]},
            metadata_={"title": "Existing Title", "custom_fields": {"priority": "high"}, "root_id": "mem-1", "updated_by": "tester"},
            obsidian_ref="note.md",
            content_hash="hash-before",
            match_key="build:arch:1",
            valid_from=None,
            created_at=now,
            updated_at=now,
        )
        session = AsyncMock()
        session.execute.return_value = SimpleNamespace(scalar_one_or_none=lambda: existing)

        updated_record = MemoryRecord(
            id="mem-1",
            match_key="build:arch:1",
            domain="build",
            entity_type="Architecture",
            title="Existing Title",
            content="after",
            owner="owner-a",
            tags=["alpha"],
            relations=MemoryRelations(related=["x"]),
            status="active",
            sensitivity="internal",
            source=SourceMetadata(),
            governance=GovernanceMetadata(),
            obsidian_ref="note.md",
            custom_fields={"priority": "high"},
            content_hash="hash-after",
            version=1,
            previous_id=None,
            root_id="mem-1",
            superseded_by=None,
            valid_from=None,
            created_at=now,
            updated_at=now,
            created_by="tester",
            updated_by="tester",
        )
        expected_out = MemoryOut(
            id="mem-1",
            domain="build",
            entity_type="Architecture",
            content="after",
            owner="owner-a",
            status="active",
            version=1,
            sensitivity="internal",
            superseded_by=None,
            tags=["alpha"],
            relations={"related": ["x"]},
            obsidian_ref="note.md",
            custom_fields={"priority": "high"},
            content_hash="hash-after",
            match_key="build:arch:1",
            previous_id=None,
            root_id="mem-1",
            valid_from=None,
            created_at=now,
            updated_at=now,
            created_by="tester",
        )

        with (
            patch.object(crud, "handle_memory_write", new=AsyncMock(return_value=MemoryWriteResponse(status="updated", record=updated_record))) as handle_write,
            patch.object(memory_writes, "get_memory", new=AsyncMock(return_value=expected_out)) as get_memory,
        ):
            result = await crud.update_memory(
                session,
                "mem-1",
                MemoryUpdate(content="after"),
                actor="auth-sub",
            )

        self.assertEqual(result, expected_out)
        request = handle_write.await_args.args[1]
        self.assertEqual(request.record.match_key, "build:arch:1")
        self.assertEqual(request.record.title, "Existing Title")
        self.assertEqual(request.record.relations.related, ["x"])
        self.assertEqual(request.record.custom_fields, {"priority": "high"})
        self.assertEqual(request.write_mode.value, "upsert")
        get_memory.assert_awaited_once_with(session, "mem-1")
        self.assertEqual(handle_write.await_args.kwargs["actor"], "auth-sub")

    async def test_update_memory_uses_append_version_for_corporate_records(self) -> None:
        now = datetime.now(timezone.utc)
        existing = Memory(
            id="mem-1",
            domain=DomainEnum.corporate,
            entity_type="Decision",
            content="before",
            embedding=None,
            owner="owner-a",
            created_by="tester",
            status="active",
            version=1,
            sensitivity="internal",
            superseded_by=None,
            tags=["alpha"],
            relations={},
            metadata_={"title": "Existing Title", "custom_fields": {"policy_area": "security"}, "root_id": "mem-1", "updated_by": "tester"},
            obsidian_ref=None,
            content_hash="hash-before",
            match_key="corp:decision:1",
            valid_from=None,
            created_at=now,
            updated_at=now,
        )
        session = AsyncMock()
        session.execute.return_value = SimpleNamespace(scalar_one_or_none=lambda: existing)

        versioned_record = MemoryRecord(
            id="mem-2",
            match_key="corp:decision:1",
            domain="corporate",
            entity_type="Decision",
            title="Existing Title",
            content="after",
            owner="owner-a",
            tags=["alpha"],
            relations=MemoryRelations(),
            status="active",
            sensitivity="internal",
            source=SourceMetadata(),
            governance=GovernanceMetadata(append_only=True, mutable=False),
            obsidian_ref=None,
            custom_fields={"policy_area": "security"},
            content_hash="hash-after",
            version=2,
            previous_id="mem-1",
            root_id="mem-1",
            superseded_by=None,
            valid_from=None,
            created_at=now,
            updated_at=now,
            created_by="tester",
            updated_by="tester",
        )

        with (
            patch.object(crud, "handle_memory_write", new=AsyncMock(return_value=MemoryWriteResponse(status="versioned", record=versioned_record))) as handle_write,
            patch.object(memory_writes, "get_memory", new=AsyncMock(return_value=MemoryOut(
                id="mem-2",
                domain="corporate",
                entity_type="Decision",
                content="after",
                owner="owner-a",
                status="active",
                version=2,
                sensitivity="internal",
                superseded_by=None,
                tags=["alpha"],
                relations={},
                obsidian_ref=None,
                custom_fields={"policy_area": "security"},
                content_hash="hash-after",
                match_key="corp:decision:1",
                previous_id="mem-1",
                root_id="mem-1",
                valid_from=None,
                created_at=now,
                updated_at=now,
                created_by="tester",
            ))),
        ):
            await crud.update_memory(session, "mem-1", MemoryUpdate(content="after"), actor="auth-sub")

        request = handle_write.await_args.args[1]
        self.assertEqual(request.write_mode.value, "append_version")
        self.assertEqual(request.record.custom_fields, {"policy_area": "security"})
        self.assertEqual(handle_write.await_args.kwargs["actor"], "auth-sub")

    async def test_update_memory_uses_upsert_for_build_decision_types(self) -> None:
        """build domain records are mutable regardless of entity_type — only corporate is append-only."""
        now = datetime.now(timezone.utc)
        existing = Memory(
            id="mem-1",
            domain=DomainEnum.build,
            entity_type="Decision",
            content="before",
            embedding=None,
            owner="owner-a",
            created_by="tester",
            status="active",
            version=1,
            sensitivity="internal",
            superseded_by=None,
            tags=["alpha"],
            relations={},
            metadata_={"title": "Existing Title", "updated_by": "tester"},
            obsidian_ref=None,
            content_hash="hash-before",
            match_key="build:decision:1",
            valid_from=None,
            created_at=now,
            updated_at=now,
        )
        session = AsyncMock()
        session.execute.return_value = SimpleNamespace(scalar_one_or_none=lambda: existing)

        with (
            patch.object(crud, "handle_memory_write", new=AsyncMock(return_value=MemoryWriteResponse(status="updated", record=None))) as handle_write,
            patch.object(memory_writes, "get_memory", new=AsyncMock(return_value=None)),
        ):
            await crud.update_memory(session, "mem-1", MemoryUpdate(content="after"), actor="auth-sub")

        request = handle_write.await_args.args[1]
        self.assertEqual(request.write_mode.value, "upsert")

    async def test_to_out_and_to_record_surface_updated_by_metadata(self) -> None:
        now = datetime.now(timezone.utc)
        existing = Memory(
            id="mem-1",
            domain=DomainEnum.build,
            entity_type="Note",
            content="payload",
            embedding=None,
            owner="owner-a",
            created_by="creator",
            status="active",
            version=1,
            sensitivity="internal",
            superseded_by=None,
            tags=[],
            relations={},
            metadata_={"updated_by": "editor", "root_id": "mem-1"},
            obsidian_ref=None,
            content_hash="hash",
            match_key="mk-1",
            valid_from=None,
            created_at=now,
            updated_at=now,
        )

        legacy = _to_out(existing)
        canonical = _to_record(existing)

        self.assertEqual(legacy.updated_by, "editor")
        self.assertEqual(canonical.updated_by, "editor")


if __name__ == "__main__":
    unittest.main()
