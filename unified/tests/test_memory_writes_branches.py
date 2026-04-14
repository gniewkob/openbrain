"""Branch coverage for src/memory_writes.py remaining uncovered paths.

Covers:
- Line 412: write mode validation failure (create_only + existing)
- Line 438: skipped (content unchanged)
- Line 714: delete_memory returns False when not found
- Lines 894-921: _normalize_owners dry_run=False path
- Lines 941-960: _fix_superseded_links dry_run=False path
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


def _make_session():
    s = AsyncMock()
    s.execute = AsyncMock()
    s.add = MagicMock(return_value=None)
    s.flush = AsyncMock()
    s.commit = AsyncMock()
    s.rollback = AsyncMock()
    return s


# ---------------------------------------------------------------------------
# Line 412 — write mode validation failure
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_memory_write_fails_on_mode_violation():
    """create_only mode with existing record → status='failed' (line 412)."""
    from src.memory_writes import handle_memory_write
    from src.schemas import MemoryWriteRecord, MemoryWriteRequest, WriteMode

    session = _make_session()
    mock_existing = MagicMock()
    mock_existing.id = "mem_existing"
    mock_existing.status = "active"

    rec = MemoryWriteRecord(
        content="test content",
        domain="build",
        entity_type="Note",
        match_key="key-1",
    )
    req = MemoryWriteRequest(record=rec, write_mode=WriteMode.create_only)

    with patch("src.memory_writes._find_existing_memory", AsyncMock(return_value=mock_existing)):
        result = await handle_memory_write(session, req)

    assert result.status == "failed"
    assert result.errors


# ---------------------------------------------------------------------------
# Line 438 — skipped (content unchanged)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_memory_write_skipped_when_content_unchanged():
    """_record_matches_existing returns True → status='skipped' (line 438)."""
    from datetime import datetime, timezone
    from src.memory_writes import handle_memory_write
    from src.schemas import MemoryRecord, MemoryWriteRecord, MemoryWriteRequest, WriteMode

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
    req = MemoryWriteRequest(record=rec, write_mode=WriteMode.upsert)

    now = datetime.now(timezone.utc)
    record_out = MemoryRecord(
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

    with (
        patch("src.memory_writes._find_existing_memory", AsyncMock(return_value=mock_existing)),
        patch("src.memory_writes._record_matches_existing", return_value=True),
        patch("src.memory_writes._to_record", return_value=record_out),
    ):
        result = await handle_memory_write(session, req)

    assert result.status == "skipped"
    assert result.record is record_out


# ---------------------------------------------------------------------------
# Line 714 — delete_memory returns False when not found
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_memory_returns_false_when_not_found():
    """Memory not found → returns False (line 714)."""
    from src.memory_writes import delete_memory

    session = _make_session()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=mock_result)

    result = await delete_memory(session, "nonexistent-id")
    assert result is False


# ---------------------------------------------------------------------------
# Lines 894-921 — _normalize_owners dry_run=False
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_normalize_owners_dry_run_false_updates_owner():
    """dry_run=False and non-append-only → updates memory.owner (lines 894-921)."""
    from src.memory_writes import _normalize_owners

    session = _make_session()
    mock_mem = MagicMock()
    mock_mem.id = "m1"
    mock_mem.owner = "old-owner"
    mock_mem.domain = "build"
    mock_mem.entity_type = "Note"

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [mock_mem]
    session.execute = AsyncMock(return_value=mock_result)

    normalize_owners = {"old-owner": "new-owner"}

    with patch("src.memory_writes._requires_append_only", return_value=False):
        actions, owners_norm = await _normalize_owners(
            session,
            dry_run=False,
            normalize_owners=normalize_owners,
        )

    assert mock_mem.owner == "new-owner"
    assert owners_norm == 1
    assert any(a.action == "normalize_owner" for a in actions)


@pytest.mark.asyncio
async def test_normalize_owners_dry_run_false_skips_append_only():
    """dry_run=False, append-only domain → policy_skip action appended (line 909-916)."""
    from src.memory_writes import _normalize_owners

    session = _make_session()
    mock_mem = MagicMock()
    mock_mem.id = "m1"
    mock_mem.owner = "old-owner"
    mock_mem.domain = "corporate"
    mock_mem.entity_type = "Decision"

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [mock_mem]
    session.execute = AsyncMock(return_value=mock_result)

    normalize_owners = {"old-owner": "new-owner"}

    with patch("src.memory_writes._requires_append_only", return_value=True):
        actions, owners_norm = await _normalize_owners(
            session,
            dry_run=False,
            normalize_owners=normalize_owners,
        )

    assert owners_norm == 0
    assert any(a.action == "policy_skip" for a in actions)


# ---------------------------------------------------------------------------
# Lines 941-960 — _fix_superseded_links dry_run=False
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fix_superseded_links_dry_run_false_fixes_link():
    """dry_run=False, non-append-only → clears superseded_by (lines 941-960)."""
    from src.memory_writes import _fix_superseded_links

    session = _make_session()
    mock_mem = MagicMock()
    mock_mem.id = "m1"
    mock_mem.superseded_by = "dead-id"
    mock_mem.status = "superseded"
    mock_mem.domain = "build"
    mock_mem.entity_type = "Note"

    # First call: get active IDs (empty set — so dead-id is NOT in active IDs)
    active_result = MagicMock()
    active_result.all.return_value = []  # no active IDs

    # Second call: get superseded memories
    superseded_result = MagicMock()
    superseded_result.scalars.return_value.all.return_value = [mock_mem]

    session.execute = AsyncMock(side_effect=[active_result, superseded_result])

    with patch("src.memory_writes._requires_append_only", return_value=False):
        actions, links_fixed = await _fix_superseded_links(session, dry_run=False)

    assert links_fixed == 1
    assert mock_mem.superseded_by is None
    assert mock_mem.status == "active"


@pytest.mark.asyncio
async def test_fix_superseded_links_dry_run_false_skips_append_only():
    """dry_run=False, append-only → policy_skip action (lines 951-959)."""
    from src.memory_writes import _fix_superseded_links

    session = _make_session()
    mock_mem = MagicMock()
    mock_mem.id = "m1"
    mock_mem.superseded_by = "dead-id"
    mock_mem.status = "superseded"
    mock_mem.domain = "corporate"
    mock_mem.entity_type = "Decision"

    active_result = MagicMock()
    active_result.all.return_value = []

    superseded_result = MagicMock()
    superseded_result.scalars.return_value.all.return_value = [mock_mem]

    session.execute = AsyncMock(side_effect=[active_result, superseded_result])

    with patch("src.memory_writes._requires_append_only", return_value=True):
        actions, links_fixed = await _fix_superseded_links(session, dry_run=False)

    assert links_fixed == 1
    assert any(a.action == "policy_skip" for a in actions)
    # status NOT changed to active (append-only)
    assert mock_mem.status == "superseded"
