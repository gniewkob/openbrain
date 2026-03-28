from __future__ import annotations

from datetime import datetime, timezone
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from src import crud
from src.models import DomainEnum, Memory
from src.schemas import MemoryCreate, MemoryWriteRecord, MemoryWriteRequest, WriteMode


class MetadataLineageTests(unittest.IsolatedAsyncioTestCase):
    async def test_handle_memory_write_create_persists_custom_fields_tenant_and_root_id(self) -> None:
        session = AsyncMock()
        session.execute.return_value = type("Result", (), {"scalar_one_or_none": lambda self: None})()
        session.commit = AsyncMock()
        session.refresh = AsyncMock()
        added: list[object] = []
        session.add = lambda obj: added.append(obj)

        async def _flush() -> None:
            now = datetime.now(timezone.utc)
            for idx, obj in enumerate(added, start=1):
                if not getattr(obj, "id", None):
                    obj.id = f"mem-{idx}"
                if not getattr(obj, "created_at", None):
                    obj.created_at = now
                if not getattr(obj, "updated_at", None):
                    obj.updated_at = now

        session.flush = AsyncMock(side_effect=_flush)

        with patch.object(crud, "get_embedding", new=AsyncMock(return_value=[0.1, 0.2])):
            result = await crud.handle_memory_write(
                session,
                MemoryWriteRequest(
                    record=MemoryWriteRecord(
                        content="note body",
                        domain="build",
                        entity_type="Note",
                        owner="owner-a",
                        tenant_id="tenant-a",
                        tags=["alpha"],
                        match_key="mk-1",
                        custom_fields={"priority": "high", "token": "abc"},
                    ),
                    write_mode=WriteMode.upsert,
                ),
            )

        self.assertEqual(result.status, "created")
        self.assertEqual(result.record.owner, "owner-a")
        self.assertEqual(result.record.tenant_id, "tenant-a")
        self.assertEqual(result.record.tags, ["alpha"])
        self.assertEqual(result.record.custom_fields, {"priority": "high", "token": "abc"})
        self.assertIsNone(result.record.previous_id)
        self.assertEqual(result.record.root_id, result.record.id)

    async def test_handle_memory_write_append_version_sets_previous_and_root_lineage(self) -> None:
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
            metadata_={"title": "Decision", "tenant_id": "tenant-a", "custom_fields": {"priority": "high"}, "root_id": "mem-1"},
            obsidian_ref=None,
            content_hash="hash-before",
            match_key="corp:decision:1",
            valid_from=None,
            created_at=now,
            updated_at=now,
        )
        session = AsyncMock()
        session.execute.return_value = SimpleNamespace(scalar_one_or_none=lambda: existing)
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

        with patch.object(crud, "get_embedding", new=AsyncMock(return_value=[0.3, 0.4])):
            result = await crud.handle_memory_write(
                session,
                MemoryWriteRequest(
                    record=MemoryWriteRecord(
                        content="after",
                        domain="corporate",
                        entity_type="Decision",
                        owner="owner-a",
                        tenant_id="tenant-a",
                        tags=["alpha", "beta"],
                        match_key="corp:decision:1",
                        custom_fields={"priority": "critical"},
                    ),
                    write_mode=WriteMode.append_version,
                ),
            )

        self.assertEqual(result.status, "versioned")
        self.assertEqual(result.record.tenant_id, "tenant-a")
        self.assertEqual(result.record.previous_id, "mem-1")
        self.assertEqual(result.record.root_id, "mem-1")
        self.assertEqual(result.record.custom_fields, {"priority": "critical"})

    async def test_store_memory_preserves_custom_fields_in_legacy_path(self) -> None:
        created = Memory(
            id="mem-1",
            domain=DomainEnum.build,
            entity_type="Note",
            content="payload",
            embedding=None,
            owner="owner-a",
            created_by="tester",
            status="active",
            version=1,
            sensitivity="internal",
            superseded_by=None,
            tags=["alpha"],
            relations={},
            metadata_={"tenant_id": "tenant-a", "custom_fields": {"priority": "high"}, "root_id": "mem-1"},
            obsidian_ref=None,
            content_hash="hash-1",
            match_key="mk-1",
            valid_from=None,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        with (
            patch.object(crud, "handle_memory_write", new=AsyncMock()) as handle_write,
            patch.object(crud, "get_memory_raw", new=AsyncMock(return_value=created)),
        ):
            handle_write.return_value = SimpleNamespace(status="created", errors=[], record=SimpleNamespace(id="mem-1"))
            result = await crud.store_memory(
                AsyncMock(),
                MemoryCreate(
                    content="payload",
                    domain="build",
                    entity_type="Note",
                    owner="owner-a",
                    tenant_id="tenant-a",
                    tags=["alpha"],
                    match_key="mk-1",
                    custom_fields={"priority": "high"},
                ),
                actor="auth-sub",
            )

        request = handle_write.await_args.args[1]
        self.assertEqual(request.record.tenant_id, "tenant-a")
        self.assertEqual(request.record.custom_fields, {"priority": "high"})
        self.assertEqual(handle_write.await_args.kwargs["actor"], "auth-sub")
        self.assertEqual(result.tenant_id, "tenant-a")
        self.assertEqual(result.custom_fields, {"priority": "high"})
        self.assertEqual(result.root_id, "mem-1")


if __name__ == "__main__":
    unittest.main()
