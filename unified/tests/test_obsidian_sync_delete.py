"""Tests for BidirectionalSyncEngine DELETED change handling."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_delete_change(source: str, memory_id: str = "mem-del"):
    from src.obsidian_sync import SyncChange, ChangeType

    return SyncChange(
        change_type=ChangeType.DELETED,
        source=source,
        memory_id=memory_id,
        obsidian_path="Memory/deleted-note.md",
        vault="TestVault",
    )


@pytest.mark.asyncio
async def test_apply_sync_deleted_obsidian_deletes_memory():
    """When source=obsidian is deleted, the corresponding memory must be deleted."""
    from src.obsidian_sync import BidirectionalSyncEngine

    engine = BidirectionalSyncEngine()
    mock_session = AsyncMock()
    mock_adapter = AsyncMock()
    change = _make_delete_change(source="obsidian")

    with patch("src.memory_writes.delete_memory", return_value=True) as mock_delete:
        result = await engine.apply_sync(mock_session, mock_adapter, change)

    assert result is True
    mock_delete.assert_called_once_with(mock_session, "mem-del", actor="obsidian-sync")


@pytest.mark.asyncio
async def test_apply_sync_deleted_openbrain_deletes_obsidian_note():
    """When source=openbrain is deleted, the Obsidian note must be deleted."""
    from src.obsidian_sync import BidirectionalSyncEngine

    engine = BidirectionalSyncEngine()
    mock_session = AsyncMock()
    mock_adapter = AsyncMock()
    mock_adapter.delete_note = AsyncMock()
    change = _make_delete_change(source="openbrain")

    result = await engine.apply_sync(mock_session, mock_adapter, change)

    assert result is True
    mock_adapter.delete_note.assert_called_once_with(
        "TestVault", "Memory/deleted-note.md"
    )


@pytest.mark.asyncio
async def test_apply_sync_deleted_removes_tracker_state():
    """DELETE handling must remove the state from the tracker."""
    from src.obsidian_sync import BidirectionalSyncEngine

    engine = BidirectionalSyncEngine()
    mock_session = AsyncMock()
    mock_adapter = AsyncMock()
    mock_adapter.delete_note = AsyncMock()
    change = _make_delete_change(source="openbrain")

    with patch.object(engine.tracker, "remove_state") as mock_remove:
        await engine.apply_sync(mock_session, mock_adapter, change)

    mock_remove.assert_called_once_with("TestVault", "Memory/deleted-note.md")


@pytest.mark.asyncio
async def test_apply_sync_deleted_corporate_memory_logs_warning_does_not_crash():
    """Corporate memories can't be hard-deleted — must log warning and still return True."""
    from src.obsidian_sync import BidirectionalSyncEngine

    engine = BidirectionalSyncEngine()
    mock_session = AsyncMock()
    mock_adapter = AsyncMock()
    change = _make_delete_change(source="obsidian")

    with patch(
        "src.memory_writes.delete_memory",
        side_effect=ValueError("Cannot hard-delete append-only memories."),
    ):
        result = await engine.apply_sync(mock_session, mock_adapter, change)

    assert result is True


@pytest.mark.asyncio
async def test_apply_sync_deleted_obsidian_note_fail_is_non_fatal():
    """If Obsidian note deletion fails, apply_sync must still return True."""
    from src.obsidian_sync import BidirectionalSyncEngine

    engine = BidirectionalSyncEngine()
    mock_session = AsyncMock()
    mock_adapter = AsyncMock()
    mock_adapter.delete_note = AsyncMock(side_effect=Exception("vault not found"))
    change = _make_delete_change(source="openbrain")

    with patch.object(engine.tracker, "remove_state"):
        result = await engine.apply_sync(mock_session, mock_adapter, change)

    assert result is True
