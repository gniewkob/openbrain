"""Tests for Obsidian conflict listing and resolution endpoints."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


def _make_session():
    s = AsyncMock()
    s.execute = AsyncMock()
    s.commit = AsyncMock()
    return s


@pytest.mark.asyncio
async def test_v1_obsidian_conflicts_returns_empty_when_no_conflicts():
    from src.api.v1.obsidian import v1_obsidian_conflicts

    session = _make_session()
    scalars_result = MagicMock()
    scalars_result.all.return_value = []
    execute_result = MagicMock()
    execute_result.scalars.return_value = scalars_result
    session.execute = AsyncMock(return_value=execute_result)

    result = await v1_obsidian_conflicts(
        vault=None, session=session, _user={"sub": "admin", "is_admin": True}
    )

    assert result.total == 0
    assert result.conflicts == []


@pytest.mark.asyncio
async def test_v1_obsidian_conflicts_returns_conflict_entries():
    from src.api.v1.obsidian import v1_obsidian_conflicts

    session = _make_session()
    mock_mem = MagicMock()
    mock_mem.id = "mem-123"
    mock_mem.content = "Test memory content"
    mock_mem.updated_at = MagicMock()
    mock_mem.metadata_ = {
        "obsidian_conflict_pending": {
            "vault": "MyVault",
            "obsidian_path": "notes/test.md",
            "detected_at": "2026-04-19T10:00:00+00:00",
        }
    }

    scalars_result = MagicMock()
    scalars_result.all.return_value = [mock_mem]
    execute_result = MagicMock()
    execute_result.scalars.return_value = scalars_result
    session.execute = AsyncMock(return_value=execute_result)

    result = await v1_obsidian_conflicts(
        vault=None, session=session, _user={"sub": "admin", "is_admin": True}
    )

    assert result.total == 1
    assert result.conflicts[0].memory_id == "mem-123"
    assert result.conflicts[0].obsidian_path == "notes/test.md"
    assert result.conflicts[0].vault == "MyVault"


@pytest.mark.asyncio
async def test_v1_obsidian_conflicts_filters_by_vault():
    from src.api.v1.obsidian import v1_obsidian_conflicts

    session = _make_session()
    mock_mem = MagicMock()
    mock_mem.id = "mem-456"
    mock_mem.content = "Another memory"
    mock_mem.updated_at = MagicMock()
    mock_mem.metadata_ = {
        "obsidian_conflict_pending": {
            "vault": "OtherVault",
            "obsidian_path": "notes/other.md",
            "detected_at": "2026-04-19T10:00:00+00:00",
        }
    }

    scalars_result = MagicMock()
    scalars_result.all.return_value = [mock_mem]
    execute_result = MagicMock()
    execute_result.scalars.return_value = scalars_result
    session.execute = AsyncMock(return_value=execute_result)

    result = await v1_obsidian_conflicts(
        vault="MyVault", session=session, _user={"sub": "admin", "is_admin": True}
    )

    assert result.total == 0


@pytest.mark.asyncio
async def test_v1_obsidian_resolve_conflict_returns_404_for_missing_memory():
    from src.api.v1.obsidian import v1_obsidian_resolve_conflict
    from fastapi import HTTPException

    session = _make_session()
    none_result = MagicMock()
    none_result.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=none_result)

    with pytest.raises(HTTPException) as exc_info:
        await v1_obsidian_resolve_conflict(
            memory_id="nonexistent",
            session=session,
            _user={"sub": "admin", "is_admin": True},
        )

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_v1_obsidian_resolve_conflict_clears_flag():
    from src.api.v1.obsidian import v1_obsidian_resolve_conflict

    session = _make_session()
    mock_mem = MagicMock()
    mock_mem.id = "mem-789"
    mock_mem.metadata_ = {
        "obsidian_conflict_pending": {
            "vault": "V",
            "obsidian_path": "p.md",
            "detected_at": "x",
        },
        "other_key": "preserved",
    }

    executed = []

    async def track_execute(stmt, *args, **kwargs):
        executed.append(stmt)
        r = MagicMock()
        r.scalar_one_or_none.return_value = mock_mem
        return r

    session.execute = track_execute
    await v1_obsidian_resolve_conflict(
        memory_id="mem-789",
        session=session,
        _user={"sub": "admin", "is_admin": True},
    )

    session.commit.assert_called_once()
    assert len(executed) == 2  # SELECT + UPDATE


@pytest.mark.asyncio
async def test_mark_conflict_pending_issues_update():
    """_mark_conflict_pending must issue an UPDATE statement."""
    from src.obsidian_sync import _mark_conflict_pending

    session = AsyncMock()
    session.execute = AsyncMock()

    await _mark_conflict_pending(session, "mem-001", "MyVault", "notes/test.md")

    session.execute.assert_called_once()
