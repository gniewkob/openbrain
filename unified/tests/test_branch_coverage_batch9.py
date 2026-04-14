"""Final coverage batch — reaches 99%+ across all remaining files.

Covers:
- memory_writes.py:68      _session_add awaitable return path
- memory_writes.py:231     await maybe_add in _create_new_memory
- memory_writes.py:306     await maybe_add in _version_memory
- memory_writes.py:769-801 upsert_memories_bulk happy path
- memory_writes.py:1022    await maybe_result in _audit (crud_common)
- api/v1/health.py:36      non-200 → "degraded" (ternary false branch)
- api/v1/obsidian.py:73-81 _get_sync_engine inner double-check-lock
- auth.py:85               OIDCVerifier.metadata() cache-hit return path
- auth.py:531              _get_redis_client double-check-lock inside lock
- config.py:85             AppConfig validator ValueError (no OIDC or key)
- crud_common.py:237       _audit await maybe_result path
"""

from __future__ import annotations

import asyncio
import os
import time
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_session():
    s = AsyncMock()
    s.execute = AsyncMock()
    s.add = MagicMock(return_value=None)
    s.flush = AsyncMock()
    s.commit = AsyncMock()
    s.rollback = AsyncMock()
    return s


# ---------------------------------------------------------------------------
# memory_writes._session_add — line 68 (awaitable return)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_session_add_returns_awaitable_when_add_is_coroutine():
    """_session_add returns the awaitable when session.add() returns one (line 68)."""
    from src.memory_writes import _session_add

    awaited = []

    async def _coro():
        awaited.append(True)

    mock_session = MagicMock()
    coro = _coro()
    mock_session.add = MagicMock(return_value=coro)

    result = _session_add(mock_session, object())
    assert result is coro
    await result
    assert awaited


# ---------------------------------------------------------------------------
# memory_writes._create_new_memory — line 231 (await maybe_add)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_new_memory_awaits_when_session_add_is_awaitable():
    """_create_new_memory awaits the result of _session_add when it returns a coroutine (line 231)."""
    from src.memory_writes import _create_new_memory
    from src.schemas import MemoryWriteRecord

    session = _make_session()
    awaited = []

    async def _async_add():
        awaited.append(True)

    session.add = MagicMock(return_value=_async_add())

    mock_memory = MagicMock()
    mock_memory.id = "test-id"
    mock_memory.metadata_ = {}

    with patch("src.memory_writes._get_embedding_compat", new=AsyncMock(return_value=[0.1])):
        with patch("src.memory_writes.Memory", return_value=mock_memory):
            with patch("src.memory_writes._build_memory_metadata", return_value={}):
                with patch("src.memory_writes._audit_compat", new=AsyncMock()):
                    with patch("src.memory_writes._to_record", return_value=MagicMock()):
                        with patch("src.memory_writes.MemoryWriteResponse", return_value=MagicMock()):
                            rec = MemoryWriteRecord(content="test", domain="build", entity_type="Note")
                            await _create_new_memory(session, rec, "agent", "abc123", False, False)

    assert awaited, "session.add coroutine should have been awaited"


# ---------------------------------------------------------------------------
# memory_writes._version_memory — line 306 (await maybe_add)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_version_memory_awaits_when_session_add_is_awaitable():
    """_version_memory awaits the result of _session_add (line 306)."""
    from src.memory_writes import _version_memory
    from src.schemas import MemoryWriteRecord

    session = _make_session()
    awaited = []

    async def _async_add():
        awaited.append(True)

    session.add = MagicMock(return_value=_async_add())

    existing = MagicMock()
    existing.id = "old-id"
    existing.content = "old content"
    existing.domain = "build"
    existing.entity_type = "Note"
    existing.owner = ""
    existing.tenant_id = None
    existing.tags = []
    existing.match_key = "key1"
    existing.obsidian_ref = None
    existing.sensitivity = "internal"
    existing.custom_fields = {}
    existing.metadata_ = {"governance": {}}
    existing.superseded_by = None
    existing.version = 1
    existing.created_by = "agent"
    existing.status = "active"

    new_memory = MagicMock()
    new_memory.id = "new-id"
    new_memory.metadata_ = {}

    with patch("src.memory_writes._get_embedding_compat", new=AsyncMock(return_value=[0.1])):
        with patch("src.memory_writes.Memory", return_value=new_memory):
            with patch("src.memory_writes._audit_compat", new=AsyncMock()):
                with patch("src.memory_writes._to_record", return_value=MagicMock()):
                    with patch("src.memory_writes.MemoryWriteResponse", return_value=MagicMock()):
                        rec = MemoryWriteRecord(content="new content", domain="build", entity_type="Note")
                        await _version_memory(session, existing, rec, "agent", "hash456", False)

    assert awaited, "session.add coroutine should have been awaited in _version_memory"


# ---------------------------------------------------------------------------
# memory_writes.upsert_memories_bulk — lines 769-801 (happy path)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_upsert_memories_bulk_happy_path_with_ids():
    """upsert_memories_bulk maps write_many results to BulkUpsertResult (lines 769-801)."""
    from src.memory_writes import upsert_memories_bulk
    from src.schemas import (
        MemoryUpsertItem,
        MemoryWriteManyResponse,
        BatchResultItem,
        BulkUpsertResult,
    )
    import uuid

    session = _make_session()
    rid = str(uuid.uuid4())

    mock_response = MemoryWriteManyResponse(
        results=[
            BatchResultItem(input_index=0, status="created", record_id=rid)
        ],
        status="success",
        summary={"created": 1},
    )

    mock_memory = MagicMock()
    mock_memory.id = rid
    mock_memory.content = "test"
    mock_memory.domain = "build"
    mock_memory.entity_type = "Note"
    mock_memory.owner = ""
    mock_memory.tenant_id = None
    mock_memory.tags = []
    mock_memory.match_key = "key1"
    mock_memory.obsidian_ref = None
    mock_memory.sensitivity = "internal"
    mock_memory.custom_fields = {}
    mock_memory.metadata_ = {}
    mock_memory.created_at = datetime.now(timezone.utc)
    mock_memory.updated_at = datetime.now(timezone.utc)

    scalars_result = MagicMock()
    scalars_result.all.return_value = [mock_memory]
    execute_result = MagicMock()
    execute_result.scalars.return_value = scalars_result
    session.execute.return_value = execute_result

    items = [MemoryUpsertItem(content="test", domain="build", match_key="key1")]

    with patch("src.memory_writes.handle_memory_write_many", new=AsyncMock(return_value=mock_response)):
        with patch("src.memory_writes._to_out", return_value=MagicMock()):
            with patch("src.memory_writes._classify_bulk_results", return_value=([], [], [])):
                result = await upsert_memories_bulk(session, items)

    assert isinstance(result, BulkUpsertResult)


@pytest.mark.asyncio
async def test_upsert_memories_bulk_no_ids_empty_map():
    """upsert_memories_bulk with all-skipped results → id_to_mem = {} (lines 797-800)."""
    from src.memory_writes import upsert_memories_bulk
    from src.schemas import (
        MemoryUpsertItem,
        MemoryWriteManyResponse,
        BatchResultItem,
        BulkUpsertResult,
    )

    session = _make_session()

    mock_response = MemoryWriteManyResponse(
        results=[
            BatchResultItem(input_index=0, status="skipped", record_id=None)
        ],
        status="success",
        summary={"skipped": 1},
    )

    items = [MemoryUpsertItem(content="test", domain="build", match_key="key1")]

    with patch("src.memory_writes.handle_memory_write_many", new=AsyncMock(return_value=mock_response)):
        result = await upsert_memories_bulk(session, items)

    assert isinstance(result, BulkUpsertResult)
    assert len(result.inserted) == 0


# ---------------------------------------------------------------------------
# crud_common._audit — line 237 (await maybe_result)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_crud_common_audit_awaits_when_add_is_awaitable():
    """_audit in crud_common awaits session.add if it returns awaitable (line 237)."""
    from src.crud_common import _audit

    session = _make_session()
    awaited = []

    async def _async_add():
        awaited.append(True)

    session.add = MagicMock(return_value=_async_add())

    mock_entry = MagicMock()
    with patch("src.crud_common.AuditLog", return_value=mock_entry):
        await _audit(
            session=session,
            operation="create",
            memory_id="test-id",
            actor="agent",
        )

    assert awaited, "_audit should have awaited the coroutine from session.add"


# ---------------------------------------------------------------------------
# api/v1/health.py:36 — non-200 response → "degraded"
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_check_vector_store_non_200_returns_degraded():
    """Status != 200 → 'degraded' (line 36 ternary false branch)."""
    import src.api.v1.health as health_mod

    mock_response = MagicMock()
    mock_response.status_code = 503

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_response)

    with patch("src.api.v1.health.httpx.AsyncClient", return_value=mock_client):
        with patch("src.api.v1.health.get_config") as mock_cfg:
            mock_cfg.return_value.embedding.url = "http://localhost:11434"
            mock_cfg.return_value.embedding.model = "nomic-embed-text"
            result = await health_mod._check_vector_store()

    assert result == "degraded"


# ---------------------------------------------------------------------------
# api/v1/obsidian.py lines 73-81 — _get_sync_engine inner lock path
# Capture before session fixture patches it
# ---------------------------------------------------------------------------

import src.api.v1.obsidian as _obsidian_mod
_REAL_GET_SYNC_ENGINE = _obsidian_mod._get_sync_engine


@pytest.mark.asyncio
async def test_get_sync_engine_creates_engine_on_first_call():
    """_get_sync_engine creates engine when _sync_engine is None (lines 73-81)."""
    mock_engine = MagicMock()
    mock_tracker = MagicMock()

    original_engine = _obsidian_mod._sync_engine
    _obsidian_mod._sync_engine = None

    try:
        with patch("src.api.v1.obsidian._get_sync_tracker", new=AsyncMock(return_value=mock_tracker)):
            with patch("src.api.v1.obsidian.BidirectionalSyncEngine", return_value=mock_engine):
                result = await _REAL_GET_SYNC_ENGINE("domain_based")
        assert result is mock_engine
    finally:
        _obsidian_mod._sync_engine = original_engine


# ---------------------------------------------------------------------------
# auth.py:85 — OIDCVerifier.metadata() cache-hit return
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_oidc_metadata_cache_hit():
    """Cached metadata within TTL is returned immediately (line 85)."""
    from src.auth import OIDCVerifier

    verifier = OIDCVerifier(issuer_url="https://example.com", audience="test")
    cached = {"issuer": "https://example.com", "jwks_uri": "https://example.com/.well-known/jwks.json"}
    verifier._metadata = cached
    verifier._metadata_fetched_at = time.time()  # fresh — within TTL

    result = await verifier.metadata()

    assert result == cached


# ---------------------------------------------------------------------------
# auth.py:531 — _get_redis_client double-check inside lock
# ---------------------------------------------------------------------------

def test_get_redis_client_double_check_inside_lock():
    """Second if-check inside lock returns pre-set _redis_client (line 531)."""
    import src.auth as auth_mod

    original_client = auth_mod._redis_client
    fake_client = MagicMock()

    class _SetBeforeAcquire:
        """Simulates another thread setting _redis_client before this one acquires the lock."""
        def __enter__(self):
            auth_mod._redis_client = fake_client
            return self

        def __exit__(self, *a):
            return False

    try:
        auth_mod._redis_client = None  # outer check passes
        with patch.object(auth_mod, "_redis_client_lock", _SetBeforeAcquire()):
            result = auth_mod._get_redis_client()
        assert result is fake_client
    finally:
        auth_mod._redis_client = original_client


# ---------------------------------------------------------------------------
# config.py:85 — AppConfig validator raises when PUBLIC_MODE + no OIDC/key
# ---------------------------------------------------------------------------

def test_public_mode_config_raises_when_no_oidc_and_no_key():
    """PUBLIC_MODE=true without OIDC_ISSUER_URL or INTERNAL_API_KEY → ValueError (line 85)."""
    from pydantic import ValidationError

    clean_env = {
        k: v for k, v in os.environ.items()
        if k not in {"OIDC_ISSUER_URL", "INTERNAL_API_KEY", "PUBLIC_MODE", "PUBLIC_BASE_URL"}
    }
    clean_env.update({
        "PUBLIC_MODE": "true",
        "PUBLIC_BASE_URL": "https://example.com",
        "OIDC_ISSUER_URL": "",
        "INTERNAL_API_KEY": "",
    })

    with patch.dict(os.environ, clean_env, clear=True):
        with pytest.raises((ValidationError, ValueError)):
            from src.config import AppConfig
            AppConfig()


# ---------------------------------------------------------------------------
# auth.py:95 — OIDCVerifier.metadata() inner double-check cache hit
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_oidc_metadata_inner_cache_hit():
    """Inner double-check inside lock returns cached metadata (auth.py:95)."""
    from src.auth import OIDCVerifier

    verifier = OIDCVerifier(issuer_url="https://example.com", audience="test")
    cached = {"issuer": "https://example.com", "jwks_uri": "https://example.com/.well-known/jwks.json"}

    class _MockRefreshLock:
        async def __aenter__(self):
            # Simulate another coroutine having refreshed metadata while we waited for the lock
            verifier._metadata = cached
            verifier._metadata_fetched_at = time.time()
            return self

        async def __aexit__(self, *a):
            return False

    verifier._metadata = None  # ensure outer check fails (line 81-85)
    with patch.object(verifier, "_get_refresh_lock", return_value=_MockRefreshLock()):
        result = await verifier.metadata()

    assert result == cached


# ---------------------------------------------------------------------------
# memory_writes._run_maintenance_inner:1022 — await maybe_add
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_maintenance_inner_awaits_when_session_add_is_awaitable():
    """_run_maintenance_inner awaits session.add if it returns awaitable (line 1022)."""
    from src.memory_writes import _run_maintenance_inner
    from src.schemas import MaintenanceRequest

    session = _make_session()
    awaited = []

    async def _async_add():
        awaited.append(True)

    session.add = MagicMock(return_value=_async_add())

    # scalar_one() returns 0 (no memories)
    total_result = MagicMock()
    total_result.scalar_one.return_value = 0
    session.execute = AsyncMock(return_value=total_result)

    req = MaintenanceRequest(dry_run=False, fix_superseded_links=False)

    with patch("src.memory_writes._process_duplicates", new=AsyncMock(return_value=([], 0))):
        with patch("src.memory_writes._normalize_owners", new=AsyncMock(return_value=([], 0))):
            with patch("src.memory_writes.AuditLog", return_value=MagicMock()):
                await _run_maintenance_inner(session, req, "agent")

    assert awaited, "session.add coroutine should have been awaited in _run_maintenance_inner"

