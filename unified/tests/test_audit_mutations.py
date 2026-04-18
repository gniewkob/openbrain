"""Tests that audit log entries are written for all mutation paths."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.ext.asyncio import AsyncSession

from src.schemas import MemoryWriteRecord


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_session():
    """Return an AsyncSession mock with minimal surface."""
    session = AsyncMock(spec=AsyncSession)
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    return session


def _make_memory(domain="build", memory_id="mem-1"):
    """Return a minimal Memory ORM stub with string domain (no .value)."""
    mem = MagicMock()
    mem.id = memory_id
    mem.domain = domain  # plain string — avoids .value branch
    mem.status = "active"
    mem.owner = "test-owner"
    mem.tenant_id = None
    mem.metadata_ = {}
    mem.content = "hello"
    mem.entity_type = "Note"
    mem.tags = []
    mem.sensitivity = "internal"
    mem.embedding = None
    mem.content_hash = "abc"
    return mem


def _stub_write_response():
    return MagicMock()


# ---------------------------------------------------------------------------
# _create_new_memory — all domains
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_logs_build_domain():
    """_create_new_memory emits audit for build domain (previously skipped)."""
    from src.memory_writes import _create_new_memory

    rec = MemoryWriteRecord(
        domain="build", entity_type="Note", content="hello", owner="u"
    )
    session = _make_session()

    with (
        patch("src.memory_writes.get_embedding", AsyncMock(return_value=None)),
        patch("src.memory_writes._audit", new_callable=AsyncMock) as mock_audit,
        patch("src.memory_writes._session_add", return_value=None),
        patch("src.memory_writes._to_record", return_value=MagicMock()),
        patch("src.memory_writes.MemoryWriteResponse", return_value=MagicMock()),
    ):
        await _create_new_memory(
            session,
            rec,
            actor="alice",
            content_hash="h",
            append_only_policy=False,
            _commit=False,
        )

    mock_audit.assert_awaited_once()
    _, posargs, kwargs = mock_audit.mock_calls[0]
    assert posargs[1] == "create"
    assert kwargs.get("meta", {}).get("domain") == "build"


@pytest.mark.asyncio
async def test_create_logs_personal_domain():
    """_create_new_memory emits audit for personal domain."""
    from src.memory_writes import _create_new_memory

    rec = MemoryWriteRecord(
        domain="personal", entity_type="Note", content="hello", owner="u"
    )
    session = _make_session()

    with (
        patch("src.memory_writes.get_embedding", AsyncMock(return_value=None)),
        patch("src.memory_writes._audit", new_callable=AsyncMock) as mock_audit,
        patch("src.memory_writes._session_add", return_value=None),
        patch("src.memory_writes._to_record", return_value=MagicMock()),
        patch("src.memory_writes.MemoryWriteResponse", return_value=MagicMock()),
    ):
        await _create_new_memory(
            session,
            rec,
            actor="alice",
            content_hash="h",
            append_only_policy=False,
            _commit=False,
        )

    mock_audit.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_logs_corporate_domain():
    """_create_new_memory still emits audit for corporate domain (regression)."""
    from src.memory_writes import _create_new_memory

    rec = MemoryWriteRecord(
        domain="corporate", entity_type="Note", content="hello", owner="u"
    )
    session = _make_session()

    with (
        patch("src.memory_writes.get_embedding", AsyncMock(return_value=None)),
        patch("src.memory_writes._audit", new_callable=AsyncMock) as mock_audit,
        patch("src.memory_writes._session_add", return_value=None),
        patch("src.memory_writes._to_record", return_value=MagicMock()),
        patch("src.memory_writes.MemoryWriteResponse", return_value=MagicMock()),
    ):
        await _create_new_memory(
            session,
            rec,
            actor="alice",
            content_hash="h",
            append_only_policy=True,
            _commit=False,
        )

    mock_audit.assert_awaited_once()
    _, posargs, kwargs = mock_audit.mock_calls[0]
    assert posargs[1] == "create"
    assert kwargs.get("meta", {}).get("domain") == "corporate"


# ---------------------------------------------------------------------------
# _update_memory — in-place update now logged
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_memory_emits_audit():
    """_update_memory emits an 'update' audit entry (previously missing)."""
    from src.memory_writes import _update_memory

    rec = MemoryWriteRecord(
        domain="build", entity_type="Note", content="updated content", owner="u"
    )
    existing = _make_memory(domain="build")
    session = _make_session()

    with (
        patch("src.memory_writes.get_embedding", AsyncMock(return_value=None)),
        patch("src.memory_writes._audit", new_callable=AsyncMock) as mock_audit,
        patch("src.memory_writes._to_record", return_value=MagicMock()),
        patch("src.memory_writes.MemoryWriteResponse", return_value=MagicMock()),
    ):
        await _update_memory(
            session, existing, rec, actor="bob", content_hash="h2", _commit=False
        )

    mock_audit.assert_awaited_once()
    _, posargs, kwargs = mock_audit.mock_calls[0]
    assert posargs[1] == "update"
    assert posargs[2] == existing.id


@pytest.mark.asyncio
async def test_update_memory_audit_contains_domain():
    """_update_memory audit meta includes the domain."""
    from src.memory_writes import _update_memory

    rec = MemoryWriteRecord(
        domain="personal", entity_type="Note", content="updated", owner="u"
    )
    existing = _make_memory(domain="personal")
    session = _make_session()

    with (
        patch("src.memory_writes.get_embedding", AsyncMock(return_value=None)),
        patch("src.memory_writes._audit", new_callable=AsyncMock) as mock_audit,
        patch("src.memory_writes._to_record", return_value=MagicMock()),
        patch("src.memory_writes.MemoryWriteResponse", return_value=MagicMock()),
    ):
        await _update_memory(
            session, existing, rec, actor="bob", content_hash="h2", _commit=False
        )

    kwargs = mock_audit.call_args[1]
    assert kwargs.get("meta", {}).get("domain") == "personal"


# ---------------------------------------------------------------------------
# Regression: _version_memory and delete_memory still log
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_version_memory_still_logged():
    """_version_memory regression — audit call still present."""
    from src.memory_writes import _version_memory

    rec = MemoryWriteRecord(
        domain="corporate", entity_type="Note", content="new version", owner="u"
    )
    existing = _make_memory(domain="corporate", memory_id="corp-1")

    session = _make_session()

    with (
        patch("src.memory_writes.get_embedding", AsyncMock(return_value=None)),
        patch("src.memory_writes._audit", new_callable=AsyncMock) as mock_audit,
        patch("src.memory_writes._session_add", return_value=None),
        patch("src.memory_writes._to_record", return_value=MagicMock()),
        patch("src.memory_writes.MemoryWriteResponse", return_value=MagicMock()),
    ):
        await _version_memory(
            session, existing, rec, actor="sys", content_hash="h3", _commit=False
        )

    mock_audit.assert_awaited_once()
    _, posargs, _ = mock_audit.mock_calls[0]
    assert posargs[1] == "version"  # _version_memory logs operation "version"


@pytest.mark.asyncio
async def test_delete_memory_still_logged():
    """delete_memory regression — audit call still present."""
    from src.memory_writes import delete_memory

    existing = _make_memory(domain="build")

    session = _make_session()
    execute_result = MagicMock()
    execute_result.scalar_one_or_none = MagicMock(return_value=existing)
    session.execute = AsyncMock(return_value=execute_result)

    with patch("src.memory_writes._audit", new_callable=AsyncMock) as mock_audit:
        await delete_memory(session, existing.id, actor="sys")

    mock_audit.assert_awaited_once()
    _, posargs, _ = mock_audit.mock_calls[0]
    assert posargs[1] == "delete"
