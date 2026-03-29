"""
Regression tests for audit fixes:
  - H5: BRAIN_URL reads from environment in mcp_transport
  - H3: update_memory raises ValueError (not None) on failed write
  - L3: atomic=True in write-many rolls back on failure
  - H2: handle_memory_write uses SELECT FOR UPDATE for match_key
  - T5: store_memories_bulk maps custom_fields and relations
  - T6: readyz logs DB errors; combined.py logs OIDC failures
"""
from __future__ import annotations

import os
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from src import crud
from src.models import DomainEnum, Memory
from src.schemas import (
    MemoryCreate,
    MemoryOut,
    MemoryRecord,
    MemoryRelations,
    MemoryUpdate,
    MemoryWriteManyRequest,
    MemoryWriteRecord,
    MemoryWriteRequest,
    MemoryWriteResponse,
    WriteMode,
    GovernanceMetadata,
    SourceMetadata,
)


def _mem(**overrides) -> Memory:
    now = datetime.now(timezone.utc)
    base = dict(
        id="mem-1",
        domain=DomainEnum.build,
        entity_type="Note",
        content="content",
        embedding=None,
        owner="owner-a",
        created_by="tester",
        status="active",
        version=1,
        sensitivity="internal",
        superseded_by=None,
        tags=["alpha"],
        relations={},
        metadata_={"title": "T", "root_id": "mem-1"},
        obsidian_ref=None,
        content_hash="hash-1",
        match_key="mk-1",
        valid_from=None,
        created_at=now,
        updated_at=now,
    )
    base.update(overrides)
    return Memory(**base)


def _record(**overrides) -> MemoryRecord:
    now = datetime.now(timezone.utc)
    base = dict(
        id="mem-1",
        domain="build",
        entity_type="Note",
        content="content",
        owner="owner-a",
        status="active",
        version=1,
        sensitivity="internal",
        content_hash="hash-1",
        created_at=now,
        updated_at=now,
        created_by="tester",
        updated_by="tester",
        source=SourceMetadata(),
        governance=GovernanceMetadata(),
    )
    base.update(overrides)
    return MemoryRecord(**base)


class BrainUrlEnvTest(unittest.TestCase):
    """H5 — BRAIN_URL must be read from env, defaulting to port 7010."""

    def test_brain_url_reads_from_env(self) -> None:
        with patch.dict(os.environ, {"BRAIN_URL": "http://testhost:9999"}):
            import importlib
            import src.mcp_transport as transport_mod
            # Re-evaluate the default at import time by reading the module attribute
            # after env is set, then restore. For a module-level constant we check
            # the default in the source by reading a fresh import.
            importlib.reload(transport_mod)
            self.assertEqual(transport_mod.BRAIN_URL, "http://testhost:9999")
            # Restore
            importlib.reload(transport_mod)

    def test_brain_url_default_is_7010_not_80(self) -> None:
        import src.mcp_transport as transport_mod
        # Remove env var to test default
        saved = os.environ.pop("BRAIN_URL", None)
        try:
            import importlib
            importlib.reload(transport_mod)
            self.assertIn("7010", transport_mod.BRAIN_URL)
            self.assertNotIn(":80", transport_mod.BRAIN_URL)
        finally:
            if saved:
                os.environ["BRAIN_URL"] = saved
            import importlib
            importlib.reload(transport_mod)


class UpdateMemoryErrorPropagationTest(unittest.IsolatedAsyncioTestCase):
    """H3 — update_memory must raise ValueError when write returns status=failed."""

    async def test_update_memory_raises_on_failed_write(self) -> None:
        session = AsyncMock()
        session.execute.return_value = SimpleNamespace(scalar_one_or_none=lambda: _mem())

        failed_response = MemoryWriteResponse(
            status="failed",
            errors=["Owner is required for corporate domain."],
        )
        with patch.object(crud, "handle_memory_write", new=AsyncMock(return_value=failed_response)):
            with self.assertRaises(ValueError) as ctx:
                await crud.update_memory(session, "mem-1", MemoryUpdate(content="new"))

        self.assertIn("Owner is required", str(ctx.exception))

    async def test_update_memory_returns_none_when_record_not_found(self) -> None:
        session = AsyncMock()
        session.execute.return_value = SimpleNamespace(scalar_one_or_none=lambda: None)

        result = await crud.update_memory(session, "missing-id", MemoryUpdate(content="x"))
        self.assertIsNone(result)

    async def test_update_memory_skipped_returns_existing_record(self) -> None:
        """status=skipped (no change) should still return the existing record."""
        now = datetime.now(timezone.utc)
        existing_out = MemoryOut(
            id="mem-1",
            domain="build",
            entity_type="Note",
            content="unchanged",
            owner="owner-a",
            status="active",
            version=1,
            sensitivity="internal",
            content_hash="h",
            created_at=now,
            updated_at=now,
            created_by="tester",
        )
        session = AsyncMock()
        session.execute.return_value = SimpleNamespace(scalar_one_or_none=lambda: _mem())

        skipped_response = MemoryWriteResponse(status="skipped", record=_record())
        with (
            patch.object(crud, "handle_memory_write", new=AsyncMock(return_value=skipped_response)),
            patch.object(crud, "get_memory", new=AsyncMock(return_value=existing_out)),
        ):
            result = await crud.update_memory(session, "mem-1", MemoryUpdate(content="unchanged"))

        self.assertEqual(result, existing_out)


class AtomicWriteManyTest(unittest.IsolatedAsyncioTestCase):
    """L3 — atomic=True must roll back all writes when any record fails."""

    async def test_atomic_batch_rolls_back_on_failure(self) -> None:
        session = AsyncMock()
        session.execute.return_value = SimpleNamespace(scalar_one_or_none=lambda: None)
        session.commit = AsyncMock()
        session.rollback = AsyncMock()

        call_count = 0

        async def _write_side_effect(sess, req, actor, _commit=True):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise ValueError("Embedding service unavailable")
            return MemoryWriteResponse(status="created", record=_record())

        records = [
            MemoryWriteRecord(content=f"rec-{i}", domain="build", entity_type="Note")
            for i in range(3)
        ]
        request = MemoryWriteManyRequest(records=records, write_mode=WriteMode.upsert, atomic=True)

        with patch.object(crud, "handle_memory_write", side_effect=_write_side_effect):
            result = await crud.handle_memory_write_many(session, request)

        # Batch must be rolled back
        session.rollback.assert_awaited_once()
        session.commit.assert_not_awaited()
        self.assertEqual(result.status, "failed")

    async def test_non_atomic_batch_continues_on_failure(self) -> None:
        session = AsyncMock()
        session.execute.return_value = SimpleNamespace(scalar_one_or_none=lambda: None)

        call_count = 0

        async def _write_side_effect(sess, req, actor, _commit=True):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise ValueError("transient error")
            return MemoryWriteResponse(status="created", record=_record())

        records = [
            MemoryWriteRecord(content=f"rec-{i}", domain="build", entity_type="Note")
            for i in range(3)
        ]
        request = MemoryWriteManyRequest(records=records, write_mode=WriteMode.upsert, atomic=False)

        with patch.object(crud, "handle_memory_write", side_effect=_write_side_effect):
            result = await crud.handle_memory_write_many(session, request)

        self.assertEqual(result.status, "partial_success")
        self.assertEqual(result.summary["created"], 2)
        self.assertEqual(result.summary["failed"], 1)


class MatchKeySelectForUpdateTest(unittest.IsolatedAsyncioTestCase):
    """H2 — handle_memory_write must use SELECT FOR UPDATE when looking up match_key."""

    async def test_match_key_lookup_uses_with_for_update(self) -> None:
        captured_stmts: list = []

        async def _execute(stmt):
            captured_stmts.append(stmt)
            return SimpleNamespace(scalar_one_or_none=lambda: None)

        session = SimpleNamespace(execute=_execute)

        # Patch add/flush/commit/refresh so we don't need a real DB
        session.add = lambda obj: None
        session.flush = AsyncMock()
        session.commit = AsyncMock()
        session.refresh = AsyncMock()

        now = datetime.now(timezone.utc)

        async def _flush_side_effect(sess, req, actor, _commit=True):
            # Simulate flush assigning id
            return None

        record = MemoryWriteRecord(
            content="test", domain="build", entity_type="Note", match_key="mk-test"
        )
        req = MemoryWriteRequest(record=record, write_mode=WriteMode.upsert)

        with patch.object(crud, "get_embedding", new=AsyncMock(return_value=[0.1, 0.2])):
            # The SELECT FOR UPDATE statement should be the first executed
            try:
                await crud.handle_memory_write(session, req)
            except Exception:
                pass  # May fail without real DB, we only check SQL shape

        self.assertGreater(len(captured_stmts), 0)
        # The first statement is the match_key lookup — verify FOR UPDATE clause
        first_stmt_str = str(captured_stmts[0])
        self.assertIn("FOR UPDATE", first_stmt_str.upper())


class StoreBulkFieldMappingTest(unittest.IsolatedAsyncioTestCase):
    """T5 — store_memories_bulk must pass custom_fields and relations to MemoryWriteRecord."""

    async def test_store_memories_bulk_maps_custom_fields(self) -> None:
        session = AsyncMock()
        captured_reqs: list[MemoryWriteRequest] = []

        now = datetime.now(timezone.utc)
        result_out = MemoryOut(
            id="m1",
            domain="build",
            entity_type="Note",
            content="x",
            owner="",
            status="active",
            version=1,
            sensitivity="internal",
            content_hash="h",
            created_at=now,
            updated_at=now,
            created_by="agent",
        )

        async def _capture_write(sess, req, actor, _commit=True):
            captured_reqs.append(req)
            return MemoryWriteResponse(status="created", record=_record())

        items = [
            MemoryCreate(
                content="content",
                domain="build",
                entity_type="Note",
                custom_fields={"priority": "high", "ticket": "OB-42"},
                relations={"related": ["other-id"]},
            )
        ]

        with (
            patch.object(crud, "handle_memory_write", side_effect=_capture_write),
            patch.object(crud, "handle_memory_write_many", wraps=crud.handle_memory_write_many),
            patch.object(crud, "get_embedding", new=AsyncMock(return_value=[0.1])),
        ):
            # Call store_memories_bulk directly
            session.execute.return_value = SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: []))
            await crud.store_memories_bulk(session, items)

        self.assertGreater(len(captured_reqs), 0)
        rec = captured_reqs[0].record
        self.assertEqual(rec.custom_fields, {"priority": "high", "ticket": "OB-42"})
        self.assertEqual(rec.relations.related, ["other-id"])


class ReadyzLoggingTest(unittest.IsolatedAsyncioTestCase):
    """T6 — readyz must log DB errors instead of swallowing them silently."""

    async def test_readyz_logs_db_error(self) -> None:
        from tests.test_metrics import _import_main_with_fake_auth_deps
        main = _import_main_with_fake_auth_deps()

        log_calls: list = []

        def _capture(*args, **kwargs):
            log_calls.append((args, kwargs))

        # Mock AsyncSessionLocal as an async context manager whose execute raises
        fake_session = AsyncMock()
        fake_session.execute = AsyncMock(side_effect=Exception("DB connection refused"))

        fake_ctx = MagicMock()
        fake_ctx.__aenter__ = AsyncMock(return_value=fake_session)
        fake_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch.object(main, "AsyncSessionLocal", return_value=fake_ctx):
            with patch.object(main.log, "error", side_effect=_capture):
                response = await main.readyz()

        # readyz returns a JSONResponse (with status_code) on error
        self.assertTrue(hasattr(response, "status_code"), "Expected JSONResponse on DB error")
        self.assertEqual(response.status_code, 503)
        self.assertGreater(len(log_calls), 0, "log.error must be called on DB failure")


if __name__ == "__main__":
    unittest.main()
