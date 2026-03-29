from __future__ import annotations

from datetime import datetime, timezone
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from src import crud
from src.models import DomainEnum, Memory
from src.schemas import MaintenanceRequest, MemoryCreate, MemoryUpsertItem, MemoryWriteRecord, MemoryWriteRequest
from tests.test_metrics import _import_main_with_fake_auth_deps


main = _import_main_with_fake_auth_deps()


class PolicyEnforcementTests(unittest.IsolatedAsyncioTestCase):
    async def test_upsert_memories_bulk_requires_match_key_for_every_record(self) -> None:
        session = AsyncMock()
        items = [
            MemoryUpsertItem(content="x", domain="build", entity_type="Note", match_key="mk-1"),
            MemoryUpsertItem(content="y", domain="build", entity_type="Note", match_key=None),
        ]

        with self.assertRaisesRegex(ValueError, "bulk-upsert requires match_key"):
            await crud.upsert_memories_bulk(session, items)

    async def test_bulk_upsert_endpoint_returns_422_when_match_key_missing(self) -> None:
        with patch.object(main, "upsert_memories_bulk", new=AsyncMock(side_effect=ValueError("bulk-upsert requires match_key"))):
            with self.assertRaises(HTTPException) as ctx:
                await main.bulk_upsert_memories(
                    data=[MemoryUpsertItem(content="x", domain="build", entity_type="Note", match_key=None)],
                    session=object(),
                    _user={"sub": "tester"},
                )

        self.assertEqual(ctx.exception.status_code, 422)

    async def test_create_memory_endpoint_returns_422_for_corporate_without_owner(self) -> None:
        data = MemoryCreate(content="x", domain="corporate", entity_type="Decision")
        with patch.object(main, "store_memory", new=AsyncMock(side_effect=ValueError("Write failed: ['Owner is required for corporate domain.']"))):
            with self.assertRaises(HTTPException) as ctx:
                await main.create_memory(
                    data=data,
                    session=object(),
                    _user={"sub": "tester"},
                )

        self.assertEqual(ctx.exception.status_code, 422)

    async def test_handle_memory_write_fails_corporate_without_match_key(self) -> None:
        """Corporate domain must require match_key to prevent permanent un-dedupable duplicates."""
        session = AsyncMock()
        session.execute.return_value = SimpleNamespace(scalar_one_or_none=lambda: None)

        rec = MemoryWriteRecord(
            content="important decision",
            domain="corporate",
            entity_type="Decision",
            owner="alice",
            # match_key intentionally omitted
        )
        result = await crud.handle_memory_write(
            session, MemoryWriteRequest(record=rec, write_mode="upsert")
        )

        self.assertEqual(result.status, "failed")
        self.assertTrue(
            any("match_key" in e for e in result.errors),
            f"Expected match_key error, got: {result.errors}",
        )

    async def test_handle_memory_write_accepts_corporate_with_match_key(self) -> None:
        """Corporate write with match_key and owner must succeed (create path)."""
        from datetime import datetime, timezone as tz
        now = datetime.now(tz.utc)

        session = AsyncMock()
        session.execute.return_value = SimpleNamespace(scalar_one_or_none=lambda: None)

        def _add(obj):
            # Simulate DB setting server defaults after flush
            obj.id = obj.id or "mem-corp-1"
            obj.created_at = now
            obj.updated_at = now

        session.add = _add
        session.flush = AsyncMock()
        session.commit = AsyncMock()
        session.refresh = AsyncMock()

        rec = MemoryWriteRecord(
            content="approved decision",
            domain="corporate",
            entity_type="Decision",
            owner="alice",
            match_key="corp:decision:approved-2026",
        )
        with patch.object(crud, "get_embedding", new=AsyncMock(return_value=[0.1, 0.2])):
            result = await crud.handle_memory_write(
                session, MemoryWriteRequest(record=rec, write_mode="upsert")
            )

        self.assertIn(result.status, {"created", "versioned"})

    async def test_handle_memory_write_sets_append_only_governance_for_corporate_domain(self) -> None:
        """Only corporate domain records get append_only=True governance, regardless of entity_type."""
        session = AsyncMock()
        session.execute.return_value = type("Result", (), {"scalar_one_or_none": lambda self: None})()
        session.commit = AsyncMock()
        session.refresh = AsyncMock()
        added = []
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
                        content="decision body",
                        domain="corporate",
                        entity_type="Decision",
                        owner="owner-a",
                        match_key="mk-1",
                    )
                ),
            )

        self.assertEqual(result.status, "created")
        memory_objs = [o for o in added if isinstance(o, Memory)]
        self.assertEqual(len(memory_objs), 1)
        governance = memory_objs[0].metadata_["governance"]
        self.assertTrue(governance["append_only"])
        self.assertFalse(governance["mutable"])

    async def test_handle_memory_write_build_decision_is_mutable(self) -> None:
        """build domain Decision must NOT be append-only — entity_type does not override domain governance."""
        session = AsyncMock()
        session.execute.return_value = type("Result", (), {"scalar_one_or_none": lambda self: None})()
        session.commit = AsyncMock()
        session.refresh = AsyncMock()
        added = []
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
                        content="build decision body",
                        domain="build",
                        entity_type="Decision",
                        owner="owner-a",
                        match_key="mk-2",
                    )
                ),
            )

        self.assertEqual(result.status, "created")
        governance = added[0].metadata_["governance"]
        self.assertFalse(governance["append_only"])
        self.assertTrue(governance["mutable"])

    async def test_delete_memory_blocks_append_only_corporate_records(self) -> None:
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
            tags=[],
            relations={},
            metadata_={},
            obsidian_ref=None,
            content_hash="hash-before",
            match_key="build:decision:1",
            valid_from=None,
            created_at=now,
            updated_at=now,
        )
        session = AsyncMock()
        session.execute.return_value = SimpleNamespace(scalar_one_or_none=lambda: existing)

        with self.assertRaisesRegex(ValueError, "append-only"):
            await crud.delete_memory(session, "mem-1")

    async def test_delete_memory_writes_audit_event_before_hard_delete(self) -> None:
        now = datetime.now(timezone.utc)
        existing = Memory(
            id="mem-1",
            domain=DomainEnum.personal,
            entity_type="Note",
            content="before",
            embedding=None,
            owner="owner-a",
            created_by="tester",
            status="active",
            version=3,
            sensitivity="internal",
            superseded_by=None,
            tags=[],
            relations={},
            metadata_={"tenant_id": "tenant-a"},
            obsidian_ref=None,
            content_hash="hash-before",
            match_key="personal:note:1",
            valid_from=None,
            created_at=now,
            updated_at=now,
        )
        session = AsyncMock()
        session.execute.return_value = SimpleNamespace(scalar_one_or_none=lambda: existing)

        with patch.object(crud, "_audit", new=AsyncMock()) as audit:
            deleted = await crud.delete_memory(session, "mem-1", actor="admin-user")

        self.assertTrue(deleted)
        audit.assert_awaited_once()
        self.assertEqual(audit.await_args.args[1], "delete")
        self.assertEqual(audit.await_args.args[2], "mem-1")
        self.assertEqual(audit.await_args.kwargs["actor"], "admin-user")
        self.assertEqual(audit.await_args.kwargs["tool_name"], "memory.delete")
        self.assertEqual(audit.await_args.kwargs["meta"]["tenant_id"], "tenant-a")
        session.delete.assert_awaited_once_with(existing)
        session.commit.assert_awaited_once()

    async def test_maintain_non_dry_run_skips_mutation_for_append_only_duplicates(self) -> None:
        now = datetime.now(timezone.utc)
        primary = Memory(
            id="mem-1",
            domain=DomainEnum.corporate,
            entity_type="Decision",
            content="same",
            embedding=[0.1, 0.2],
            owner="owner-a",
            created_by="tester",
            status="active",
            version=1,
            sensitivity="internal",
            superseded_by=None,
            tags=[],
            relations={},
            metadata_={},
            obsidian_ref=None,
            content_hash="hash-same",
            match_key="corp:decision:1",
            valid_from=None,
            created_at=now,
            updated_at=now,
        )
        duplicate = Memory(
            id="mem-2",
            domain=DomainEnum.corporate,
            entity_type="Decision",
            content="same",
            embedding=[0.1, 0.2],
            owner="owner-b",
            created_by="tester",
            status="active",
            version=1,
            sensitivity="internal",
            superseded_by=None,
            tags=[],
            relations={},
            metadata_={},
            obsidian_ref=None,
            content_hash="hash-same",
            match_key="corp:decision:2",
            valid_from=None,
            created_at=now,
            updated_at=now,
        )
        session = AsyncMock()
        session.execute.side_effect = [
            SimpleNamespace(scalar_one=lambda: 2),
            SimpleNamespace(all=lambda: [("hash-same", "Decision", DomainEnum.corporate)]),
            SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: [primary, duplicate])),
        ]
        session.add = lambda obj: None
        session.flush = AsyncMock()
        session.commit = AsyncMock()

        report = await crud.run_maintenance(
            session,
            MaintenanceRequest(dry_run=False, dedup_threshold=0.05, fix_superseded_links=False),
            actor="tester",
        )

        self.assertEqual(report.dedup_found, 1)
        self.assertEqual(duplicate.status, "active")
        self.assertIsNone(duplicate.superseded_by)
        self.assertTrue(any(action.action == "policy_skip" for action in report.actions))

    async def test_maintenance_dedup_override_supersedes_append_only_exact_duplicates(self) -> None:
        """allow_exact_dedup_override=True must supersede append-only exact duplicates (governance-safe)."""
        now = datetime.now(timezone.utc)

        def _make_mem(mem_id, match_key):
            return Memory(
                id=mem_id, domain=DomainEnum.corporate, entity_type="Decision",
                content="same corporate content", embedding=[0.1, 0.2],
                owner="owner-a", created_by="tester", status="active", version=1,
                sensitivity="internal", superseded_by=None, tags=[], relations={},
                metadata_={}, obsidian_ref=None, content_hash="hash-corp",
                match_key=match_key, valid_from=None, created_at=now, updated_at=now,
            )

        canonical = _make_mem("corp-1", "corp:decision:1")
        duplicate = _make_mem("corp-2", "corp:decision:2")

        session = AsyncMock()
        session.execute.side_effect = [
            SimpleNamespace(scalar_one=lambda: 2),
            SimpleNamespace(all=lambda: [("hash-corp", "Decision", DomainEnum.corporate)]),
            SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: [canonical, duplicate])),
        ]
        session.add = lambda obj: None
        session.flush = AsyncMock()
        session.commit = AsyncMock()

        report = await crud.run_maintenance(
            session,
            MaintenanceRequest(
                dry_run=False, dedup_threshold=0.05,
                fix_superseded_links=False, allow_exact_dedup_override=True,
            ),
            actor="tester",
        )

        # Duplicate must be superseded, canonical must stay active
        self.assertEqual(duplicate.status, "superseded")
        self.assertEqual(duplicate.superseded_by, "corp-1")
        self.assertEqual(canonical.status, "active")
        self.assertTrue(any(action.action == "dedup_override" for action in report.actions))
        self.assertFalse(any(action.action == "policy_skip" for action in report.actions))

    async def test_maintenance_dedup_override_false_still_skips_append_only(self) -> None:
        """Without allow_exact_dedup_override, append-only duplicates must still get policy_skip."""
        now = datetime.now(timezone.utc)
        canonical = Memory(
            id="corp-1", domain=DomainEnum.corporate, entity_type="Decision",
            content="x", embedding=[0.1], owner="owner-a", created_by="tester",
            status="active", version=1, sensitivity="internal", superseded_by=None,
            tags=[], relations={}, metadata_={}, obsidian_ref=None, content_hash="h",
            match_key="corp:1", valid_from=None, created_at=now, updated_at=now,
        )
        duplicate = Memory(
            id="corp-2", domain=DomainEnum.corporate, entity_type="Decision",
            content="x", embedding=[0.1], owner="owner-a", created_by="tester",
            status="active", version=1, sensitivity="internal", superseded_by=None,
            tags=[], relations={}, metadata_={}, obsidian_ref=None, content_hash="h",
            match_key="corp:2", valid_from=None, created_at=now, updated_at=now,
        )
        session = AsyncMock()
        session.execute.side_effect = [
            SimpleNamespace(scalar_one=lambda: 2),
            SimpleNamespace(all=lambda: [("h", "Decision", DomainEnum.corporate)]),
            SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: [canonical, duplicate])),
        ]
        session.add = lambda obj: None
        session.flush = AsyncMock()
        session.commit = AsyncMock()

        report = await crud.run_maintenance(
            session,
            MaintenanceRequest(dry_run=False, dedup_threshold=0.05,
                               fix_superseded_links=False, allow_exact_dedup_override=False),
            actor="tester",
        )

        self.assertEqual(duplicate.status, "active")  # must NOT be mutated
        self.assertTrue(any(action.action == "policy_skip" for action in report.actions))

    async def test_ingest_warns_on_missing_match_key_for_build_domain(self) -> None:
        """build/personal writes without match_key must trigger a duplicate_risk_write warning."""
        import logging
        session = AsyncMock()
        session.execute.return_value = SimpleNamespace(scalar_one_or_none=lambda: None)
        session.add = lambda obj: None
        session.flush = AsyncMock()
        session.commit = AsyncMock()
        session.refresh = AsyncMock()

        warning_events: list[str] = []

        original_warning = crud.log.warning

        def _capture_warning(event, **kw):
            warning_events.append(event)

        from unittest.mock import patch
        with patch.object(crud.log, "warning", side_effect=_capture_warning):
            with patch.object(crud, "get_embedding", new=AsyncMock(return_value=[0.1])):
                rec = MemoryWriteRecord(
                    content="no match key write",
                    domain="build",
                    entity_type="Note",
                    # match_key intentionally absent
                )
                try:
                    await crud.handle_memory_write(
                        session, MemoryWriteRequest(record=rec, write_mode="upsert")
                    )
                except Exception:
                    pass  # May fail without full DB; we only check the warning

        self.assertIn("duplicate_risk_write", warning_events,
                      "Expected duplicate_risk_write warning for build write without match_key")


if __name__ == "__main__":
    unittest.main()
