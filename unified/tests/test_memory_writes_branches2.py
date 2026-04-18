"""Branch coverage batch 2 for src/memory_writes.py remaining uncovered paths.

Covers:
- Line 446: truncation warning appended in version path
- Line 451: truncation warning appended in update path
- Line 548: atomic batch commit (session.commit called)
- Line 604: store_memory raises ValueError on failed write
- Line 634: store_memories_bulk returns [] when no IDs
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone


def _make_session():
    s = AsyncMock()
    s.execute = AsyncMock()
    s.add = MagicMock(return_value=None)
    s.flush = AsyncMock()
    s.commit = AsyncMock()
    s.rollback = AsyncMock()
    return s


def _make_memory_record():
    from src.schemas import MemoryRecord

    now = datetime.now(timezone.utc)
    return MemoryRecord(
        id="mem_1",
        domain="build",
        entity_type="Note",
        content="test content",
        owner="agent",
        content_hash="hash123",
        created_at=now,
        updated_at=now,
        created_by="agent",
        updated_by="agent",
    )


# ---------------------------------------------------------------------------
# Line 446 — truncation warning in version path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_memory_write_appends_truncation_warning_in_version_path():
    """_warn_if_truncated returns warning + version path taken → warning appended (line 446)."""
    from src.memory_writes import handle_memory_write
    from src.schemas import (
        MemoryWriteRecord,
        MemoryWriteRequest,
        WriteMode,
        MemoryWriteResponse,
    )

    session = _make_session()
    mock_existing = MagicMock()
    mock_existing.id = "mem_1"
    mock_existing.status = "active"
    mock_existing.domain = "build"
    mock_existing.entity_type = "Note"

    rec = MemoryWriteRecord(
        content="test content",
        domain="build",
        entity_type="Note",
        match_key="key-1",
    )
    # append_version mode → takes the version path (line 441)
    req = MemoryWriteRequest(record=rec, write_mode=WriteMode.append_version)

    version_result = MemoryWriteResponse(
        status="created",
        record=_make_memory_record(),
        warnings=[],
    )

    with (
        patch(
            "src.memory_writes._find_existing_memory",
            AsyncMock(return_value=mock_existing),
        ),
        patch("src.memory_writes._record_matches_existing", return_value=False),
        patch(
            "src.memory_writes._warn_if_truncated",
            return_value="content truncated warning",
        ),
        patch("src.memory_writes._requires_append_only", return_value=False),
        patch(
            "src.memory_writes._version_memory", AsyncMock(return_value=version_result)
        ),
    ):
        result = await handle_memory_write(session, req)

    assert result.status == "created"
    assert "content truncated warning" in result.warnings


# ---------------------------------------------------------------------------
# Line 451 — truncation warning in update path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_memory_write_appends_truncation_warning_in_update_path():
    """_warn_if_truncated returns warning + update path taken → warning appended (line 451)."""
    from src.memory_writes import handle_memory_write
    from src.schemas import (
        MemoryWriteRecord,
        MemoryWriteRequest,
        WriteMode,
        MemoryWriteResponse,
    )

    session = _make_session()
    mock_existing = MagicMock()
    mock_existing.id = "mem_1"
    mock_existing.status = "active"
    mock_existing.domain = "build"
    mock_existing.entity_type = "Note"

    rec = MemoryWriteRecord(
        content="test content",
        domain="build",
        entity_type="Note",
        match_key="key-2",
    )
    # upsert mode + non-append-only domain → update path (line 449)
    req = MemoryWriteRequest(record=rec, write_mode=WriteMode.upsert)

    update_result = MemoryWriteResponse(
        status="updated",
        record=_make_memory_record(),
        warnings=[],
    )

    with (
        patch(
            "src.memory_writes._find_existing_memory",
            AsyncMock(return_value=mock_existing),
        ),
        patch("src.memory_writes._record_matches_existing", return_value=False),
        patch(
            "src.memory_writes._warn_if_truncated",
            return_value="content truncated warning",
        ),
        patch("src.memory_writes._requires_append_only", return_value=False),
        patch(
            "src.memory_writes._update_memory", AsyncMock(return_value=update_result)
        ),
    ):
        result = await handle_memory_write(session, req)

    assert result.status == "updated"
    assert "content truncated warning" in result.warnings


# ---------------------------------------------------------------------------
# Line 548 — atomic batch commit
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_memory_write_many_atomic_commits_on_success():
    """atomic=True + all succeed → session.commit() called (line 548)."""
    from src.memory_writes import handle_memory_write_many
    from src.schemas import (
        MemoryWriteRecord,
        MemoryWriteManyRequest,
        WriteMode,
        MemoryWriteResponse,
    )

    session = _make_session()

    # Batch lookup: session.execute returns result with .all() returning []
    batch_mock = MagicMock()
    batch_mock.all.return_value = []
    session.execute = AsyncMock(return_value=batch_mock)

    rec = MemoryWriteRecord(
        content="test content",
        domain="build",
        entity_type="Note",
        match_key="key-atomic",
    )
    req = MemoryWriteManyRequest(
        records=[rec], write_mode=WriteMode.upsert, atomic=True
    )

    write_result = MemoryWriteResponse(
        status="created",
        record=_make_memory_record(),
        warnings=[],
    )

    with patch(
        "src.memory_writes.handle_memory_write", AsyncMock(return_value=write_result)
    ):
        response = await handle_memory_write_many(session, req)

    # session.commit() was called (line 548)
    session.commit.assert_awaited_once()
    assert response.status != "failed"


# ---------------------------------------------------------------------------
# Line 604 — store_memory raises ValueError on failed write
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_store_memory_raises_on_failed_write():
    """handle_memory_write returns failed → store_memory raises ValueError (line 604)."""
    from src.memory_writes import store_memory
    from src.schemas import MemoryCreate, MemoryWriteResponse

    session = _make_session()

    item = MemoryCreate(
        content="test content",
        domain="build",
        entity_type="Note",
        owner="agent",
    )

    failed_result = MemoryWriteResponse(
        status="failed",
        errors=["write validation failed"],
    )

    with patch(
        "src.memory_writes.handle_memory_write", AsyncMock(return_value=failed_result)
    ):
        with pytest.raises(ValueError, match="Write failed"):
            await store_memory(session, item)


# ---------------------------------------------------------------------------
# Line 634 — store_memories_bulk returns [] when no IDs
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_store_memories_bulk_returns_empty_when_no_ids():
    """All results have no record_id → store_memories_bulk returns [] (line 634)."""
    from src.memory_writes import store_memories_bulk
    from src.schemas import MemoryCreate, MemoryWriteManyResponse, BatchResultItem

    session = _make_session()

    items = [
        MemoryCreate(
            content="test",
            domain="build",
            entity_type="Note",
            owner="agent",
        )
    ]

    # All results have no record_id
    no_id_result = MemoryWriteManyResponse(
        status="failed",
        summary={"received": 1, "created": 0, "failed": 1},
        results=[
            BatchResultItem(
                input_index=0,
                status="failed",
                match_key=None,
                record_id=None,
            )
        ],
    )

    with patch(
        "src.memory_writes.handle_memory_write_many",
        AsyncMock(return_value=no_id_result),
    ):
        result = await store_memories_bulk(session, items)

    assert result == []
