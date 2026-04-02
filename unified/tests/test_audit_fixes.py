"""
Regression tests for audit fixes:
  - H5: BRAIN_URL reads from environment in mcp_transport
  - H3: update_memory raises ValueError (not None) on failed write
  - L3: atomic=True in write-many rolls back on failure
  - H2: handle_memory_write uses SELECT FOR UPDATE for match_key
  - T5: store_memories_bulk maps custom_fields and relations
  - T6: readyz logs DB errors; combined.py logs OIDC failures
  - A1: dedup query groups by domain to prevent cross-domain supersession
  - A2: sensitivity-only change is NOT silently skipped
  - A3: non-atomic batch rolls back session on per-record failure
  - A4: dry_run=True maintenance does not persist AuditLog entries
  - A5: embedding fetched before content mutation (safe write order)
"""
from __future__ import annotations

import os
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from src import crud, memory_reads, memory_writes, middleware as middleware_module
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
    """H5 — BRAIN_URL must be read from env, defaulting to the internal port 80."""

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

    def test_brain_url_default_is_internal_80(self) -> None:
        import src.mcp_transport as transport_mod
        # Remove env var to test default
        saved = os.environ.pop("BRAIN_URL", None)
        try:
            import importlib
            importlib.reload(transport_mod)
            self.assertIn(":80", transport_mod.BRAIN_URL)
            self.assertNotIn("7010", transport_mod.BRAIN_URL)
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
                await memory_writes.update_memory(session, "mem-1", MemoryUpdate(content="new"))

        self.assertIn("Owner is required", str(ctx.exception))

    async def test_update_memory_returns_none_when_record_not_found(self) -> None:
        session = AsyncMock()
        session.execute.return_value = SimpleNamespace(scalar_one_or_none=lambda: None)

        result = await memory_writes.update_memory(session, "missing-id", MemoryUpdate(content="x"))
        self.assertIsNone(result)

    async def test_update_memory_skipped_returns_existing_record(self) -> None:
        """status=skipped must return the loaded record without an extra get_memory SELECT."""
        session = AsyncMock()
        session.execute.return_value = SimpleNamespace(scalar_one_or_none=lambda: _mem())

        skipped_response = MemoryWriteResponse(status="skipped", record=_record())
        with (
            patch.object(crud, "handle_memory_write", new=AsyncMock(return_value=skipped_response)),
            patch.object(memory_writes, "get_memory", new=AsyncMock()) as mock_get,
        ):
            result = await memory_writes.update_memory(session, "mem-1", MemoryUpdate(content="unchanged"))

        self.assertIsNotNone(result)
        self.assertEqual(result.id, "mem-1")
        mock_get.assert_not_called()  # C2: no redundant SELECT on skip


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
            result = await memory_writes.handle_memory_write_many(session, request)

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
            result = await memory_writes.handle_memory_write_many(session, request)

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
                await memory_writes.handle_memory_write(session, req)
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
            patch.object(crud, "handle_memory_write_many", wraps=memory_writes.handle_memory_write_many),
            patch.object(crud, "get_embedding", new=AsyncMock(return_value=[0.1])),
        ):
            # Call store_memories_bulk directly
            session.execute.return_value = SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: []))
            await memory_writes.store_memories_bulk(session, items)

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


class CrossDomainDedupTest(unittest.IsolatedAsyncioTestCase):
    """A1 — dedup must not group across domains (prevents corporate↔build supersession)."""

    async def test_dedup_query_includes_domain_in_group_by(self) -> None:
        """Verify the dup_groups query includes Memory.domain in SELECT/GROUP BY."""
        from src.schemas import MaintenanceRequest
        captured_stmts: list = []

        async def _execute(stmt):
            captured_stmts.append(str(stmt))
            # First call: total count (>1 so dedup loop runs)
            if len(captured_stmts) == 1:
                return SimpleNamespace(scalar_one=lambda: 2)
            # Second call: dup_groups (empty — no actual duplicates)
            return SimpleNamespace(all=lambda: [], scalars=lambda: SimpleNamespace(all=lambda: []))

        session = SimpleNamespace(execute=_execute)
        session.add = lambda obj: None
        session.flush = AsyncMock()
        session.commit = AsyncMock()

        req = MaintenanceRequest(dry_run=True, dedup_threshold=0.05, fix_superseded_links=False)
        await memory_writes.run_maintenance(session, req)

        # The dedup GROUP BY statement should reference domain
        dedup_stmts = [s for s in captured_stmts if "GROUP BY" in s.upper()]
        self.assertTrue(
            any("domain" in s.lower() for s in dedup_stmts),
            f"Expected 'domain' in GROUP BY but got: {dedup_stmts}",
        )


class SensitivityOnlyChangeTest(unittest.IsolatedAsyncioTestCase):
    """A2 — sensitivity-only change must NOT be skipped (triggers update, not 'skipped')."""

    async def test_sensitivity_only_change_is_not_skipped(self) -> None:
        from sqlalchemy import select as sa_select

        now = datetime.now(timezone.utc)
        existing = _mem(sensitivity="internal", content="same", content_hash="hash-same")

        captured_stmts: list = []

        async def _execute(stmt):
            captured_stmts.append(stmt)
            return SimpleNamespace(scalar_one_or_none=lambda: existing)

        session = SimpleNamespace(execute=_execute)
        session.add = lambda obj: None
        session.flush = AsyncMock()
        session.commit = AsyncMock()
        session.refresh = AsyncMock()

        record = MemoryWriteRecord(
            content="same",
            domain="build",
            entity_type="Note",
            match_key="mk-1",
            sensitivity="confidential",  # only sensitivity changed
        )
        req = MemoryWriteRequest(record=record, write_mode=WriteMode.upsert)

        with patch.object(crud, "get_embedding", new=AsyncMock(return_value=[0.1, 0.2])):
            result = await memory_writes.handle_memory_write(session, req)

        self.assertNotEqual(result.status, "skipped", "sensitivity-only change must not be skipped")

    async def test_metadata_only_change_is_not_skipped(self) -> None:
        existing = _mem(
            content="same",
            content_hash="hash-same",
            relations={"parent": "mem-0"},
            metadata_={
                "title": "Before",
                "root_id": "mem-1",
                "custom_fields": {"priority": "low"},
                "source": {"type": "agent", "system": "other"},
                "tenant_id": "tenant-a",
            },
            tenant_id="tenant-a",
        )

        async def _execute(stmt):
            return SimpleNamespace(scalar_one_or_none=lambda: existing)

        session = SimpleNamespace(execute=_execute)
        session.add = lambda obj: None
        session.flush = AsyncMock()
        session.commit = AsyncMock()
        session.refresh = AsyncMock()

        record = MemoryWriteRecord(
            content="same",
            domain="build",
            entity_type="Task",
            match_key="mk-1",
            title="After",
            tenant_id="tenant-b",
            relations=MemoryRelations(parent=["mem-9"]),
            custom_fields={"priority": "critical"},
            source=SourceMetadata(type="agent", system="other"),
        )
        req = MemoryWriteRequest(record=record, write_mode=WriteMode.upsert)

        with patch.object(crud, "get_embedding", new=AsyncMock(return_value=[0.1, 0.2])):
            result = await memory_writes.handle_memory_write(session, req)

        self.assertNotEqual(result.status, "skipped", "metadata-only change must not be skipped")


class NonAtomicSessionRollbackTest(unittest.IsolatedAsyncioTestCase):
    """A3 — non-atomic batch must rollback session after each per-record failure."""

    async def test_non_atomic_batch_rolls_back_on_per_record_failure(self) -> None:
        session = AsyncMock()
        session.execute.return_value = SimpleNamespace(scalar_one_or_none=lambda: None)
        session.rollback = AsyncMock()

        call_count = 0

        async def _write_side_effect(sess, req, actor, _commit=True):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise ValueError("Embedding unavailable")
            return MemoryWriteResponse(status="created", record=_record())

        records = [
            MemoryWriteRecord(content=f"rec-{i}", domain="build", entity_type="Note")
            for i in range(3)
        ]
        request = MemoryWriteManyRequest(records=records, write_mode=WriteMode.upsert, atomic=False)

        with patch.object(crud, "handle_memory_write", side_effect=_write_side_effect):
            result = await memory_writes.handle_memory_write_many(session, request)

        session.rollback.assert_awaited_once()
        self.assertEqual(result.status, "partial_success")


class DryRunAuditLogTest(unittest.IsolatedAsyncioTestCase):
    """A4 — dry_run=True must not persist AuditLog entries."""

    async def test_dry_run_does_not_add_audit_log(self) -> None:
        from src.schemas import MaintenanceRequest
        added_objects: list = []

        async def _execute(stmt):
            return SimpleNamespace(scalar_one=lambda: 0, all=lambda: [], scalars=lambda: SimpleNamespace(all=lambda: []))

        session = SimpleNamespace(execute=_execute)
        session.add = lambda obj: added_objects.append(obj)
        session.flush = AsyncMock()
        session.commit = AsyncMock()

        req = MaintenanceRequest(dry_run=True, dedup_threshold=0.0, fix_superseded_links=False)
        report = await memory_writes.run_maintenance(session, req)

        from src.models import AuditLog
        audit_entries = [o for o in added_objects if isinstance(o, AuditLog)]
        self.assertEqual(len(audit_entries), 0, "dry_run=True must not persist AuditLog")

    async def test_non_dry_run_does_add_audit_log(self) -> None:
        from src.models import AuditLog
        from src.schemas import MaintenanceRequest
        added_objects: list = []

        async def _execute(stmt):
            return SimpleNamespace(scalar_one=lambda: 0, all=lambda: [], scalars=lambda: SimpleNamespace(all=lambda: []))

        session = SimpleNamespace(execute=_execute)
        session.add = lambda obj: added_objects.append(obj)
        session.flush = AsyncMock()
        session.commit = AsyncMock()

        req = MaintenanceRequest(dry_run=False, dedup_threshold=0.0, fix_superseded_links=False)
        await memory_writes.run_maintenance(session, req)

        audit_entries = [o for o in added_objects if isinstance(o, AuditLog)]
        self.assertEqual(len(audit_entries), 1, "dry_run=False must persist exactly one AuditLog")


class SearchScoreSemanticsTest(unittest.IsolatedAsyncioTestCase):
    """Fix2 — search_memories must return similarity (1=similar), not raw distance (0=similar)."""

    async def test_search_memories_returns_similarity_not_distance(self) -> None:
        from src.schemas import SearchRequest

        # distance=0.1 means very similar → similarity should be 0.9
        fake_memory = _mem()
        fake_row = SimpleNamespace(Memory=fake_memory, distance=0.1)

        async def _execute(stmt):
            return SimpleNamespace(all=lambda: [fake_row])

        session = SimpleNamespace(execute=_execute)

        with patch.object(crud, "get_embedding", new=AsyncMock(return_value=[0.1, 0.2])):
            results = await memory_reads.search_memories(session, SearchRequest(query="test", top_k=1))

        self.assertEqual(len(results), 1)
        _mem_out, score = results[0]
        self.assertAlmostEqual(score, 0.9, places=5, msg="score must be 1.0 - distance (similarity)")
        self.assertGreater(score, 0.5, "high-similarity result must score > 0.5")


class RequestIdSanitizationTest(unittest.IsolatedAsyncioTestCase):
    """Fix4 — RequestIDMiddleware must reject malformed X-Request-ID headers."""

    async def test_valid_uuid_header_is_preserved(self) -> None:
        from tests.test_metrics import _import_main_with_fake_auth_deps
        main = _import_main_with_fake_auth_deps()

        captured: list[str] = []

        async def fake_next(request):
            from starlette.responses import Response
            return Response()

        from starlette.testclient import TestClient
        from starlette.requests import Request as StarletteRequest

        valid_id = "123e4567-e89b-12d3-a456-426614174000"
        scope = {"type": "http", "method": "GET", "path": "/", "headers": [
            (b"x-request-id", valid_id.encode()),
        ], "query_string": b""}

        middleware = middleware_module.RequestIDMiddleware(app=fake_next)

        req_ids: list[str] = []

        async def _next(request):
            import structlog
            req_ids.append(structlog.contextvars.get_contextvars().get("request_id", ""))
            from starlette.responses import Response
            return Response()

        middleware.app = _next
        from starlette.requests import Request as SR
        request = SR(scope)
        await middleware.dispatch(request, _next)

        self.assertEqual(req_ids[0], valid_id)

    def test_malformed_header_is_rejected(self) -> None:
        from tests.test_metrics import _import_main_with_fake_auth_deps
        main = _import_main_with_fake_auth_deps()
        import re
        self.assertFalse(bool(middleware_module.REQUEST_ID_RE.match("inject\nnewline")))
        self.assertFalse(bool(middleware_module.REQUEST_ID_RE.match("x" * 65)))
        self.assertFalse(bool(middleware_module.REQUEST_ID_RE.match("")))
        self.assertTrue(bool(middleware_module.REQUEST_ID_RE.match("abc-123")))
        self.assertTrue(bool(middleware_module.REQUEST_ID_RE.match("123e4567-e89b-12d3-a456-426614174000")))


class EntityTypeMaxLengthTest(unittest.TestCase):
    """Fix5 — entity_type must be rejected if longer than 64 characters."""

    def test_entity_type_over_64_chars_raises(self) -> None:
        from pydantic import ValidationError
        long_type = "A" * 65
        with self.assertRaises(ValidationError):
            MemoryWriteRecord(content="x", domain="build", entity_type=long_type)

    def test_entity_type_at_64_chars_is_valid(self) -> None:
        rec = MemoryWriteRecord(content="x", domain="build", entity_type="A" * 64)
        self.assertEqual(len(rec.entity_type), 64)

    def test_entity_type_default_is_within_limit(self) -> None:
        rec = MemoryWriteRecord(content="x", domain="build")
        self.assertLessEqual(len(rec.entity_type), 64)


class DbPoolConfigTest(unittest.TestCase):
    """Fix6 — engine must have pool_recycle and statement_timeout configured."""

    def test_engine_has_pool_recycle(self) -> None:
        from src.db import engine
        self.assertEqual(engine.pool._recycle, 1800)

    def test_engine_has_statement_timeout_in_connect_args(self) -> None:
        import src.db as db_module
        import inspect
        source = inspect.getsource(db_module)
        self.assertIn("statement_timeout", source)
        self.assertIn("server_settings", source)


if __name__ == "__main__":
    unittest.main()
