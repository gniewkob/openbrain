"""Tests for BidirectionalSyncEngine export (OpenBrain → Obsidian)."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_openbrain_change():
    from src.obsidian_sync import SyncChange, ChangeType

    return SyncChange(
        change_type=ChangeType.CREATED,
        source="openbrain",
        memory_id="mem-42",
        obsidian_path="Memory/my-note.md",
        vault="TestVault",
    )


def _make_conflict_change():
    from src.obsidian_sync import SyncChange, ChangeType

    return SyncChange(
        change_type=ChangeType.UPDATED,
        source="both",
        conflict=True,
        memory_id="mem-99",
        obsidian_path="Memory/conflict-note.md",
        vault="TestVault",
    )


def _make_memory(memory_id: str = "mem-42"):
    mem = MagicMock()
    mem.id = memory_id
    mem.content = "Memory content here"
    mem.domain = "build"
    mem.custom_fields = {"title": "My Note"}
    return mem


def _written_note(
    path: str = "Memory/my-note.md", content: str = "Memory content here"
):
    note = MagicMock()
    note.path = path
    note.content = content
    return note


@pytest.mark.asyncio
async def test_apply_sync_created_openbrain_exports_to_obsidian():
    """apply_sync CREATED/openbrain must write a note to Obsidian."""
    from src.obsidian_sync import BidirectionalSyncEngine

    engine = BidirectionalSyncEngine()
    mock_session = AsyncMock()
    mock_adapter = AsyncMock()
    mock_adapter.write_note = AsyncMock(return_value=_written_note())
    change = _make_openbrain_change()

    with patch("src.memory_reads.get_memory", return_value=_make_memory()):
        with patch(
            "src.services.converter.memory_to_note_content", return_value="# content"
        ):
            with patch("src.services.converter.memory_to_frontmatter", return_value={}):
                result = await engine.apply_sync(mock_session, mock_adapter, change)

    assert result is True
    mock_adapter.write_note.assert_called_once()
    call_kwargs = mock_adapter.write_note.call_args[1]
    assert call_kwargs["vault"] == "TestVault"
    assert call_kwargs["path"] == "Memory/my-note.md"
    assert call_kwargs["overwrite"] is False


@pytest.mark.asyncio
async def test_apply_sync_created_openbrain_updates_tracker():
    """apply_sync CREATED/openbrain must record sync state after export."""
    from src.obsidian_sync import BidirectionalSyncEngine

    engine = BidirectionalSyncEngine()
    mock_session = AsyncMock()
    mock_adapter = AsyncMock()
    mock_adapter.write_note = AsyncMock(return_value=_written_note())
    change = _make_openbrain_change()

    with patch("src.memory_reads.get_memory", return_value=_make_memory()):
        with patch(
            "src.services.converter.memory_to_note_content", return_value="# content"
        ):
            with patch("src.services.converter.memory_to_frontmatter", return_value={}):
                with patch.object(engine.tracker, "update_state") as mock_update_state:
                    await engine.apply_sync(mock_session, mock_adapter, change)

    mock_update_state.assert_called_once()


@pytest.mark.asyncio
async def test_apply_sync_created_openbrain_memory_not_found_is_noop():
    """apply_sync CREATED/openbrain must skip gracefully if memory no longer exists."""
    from src.obsidian_sync import BidirectionalSyncEngine

    engine = BidirectionalSyncEngine()
    mock_session = AsyncMock()
    mock_adapter = AsyncMock()
    change = _make_openbrain_change()

    with patch("src.memory_reads.get_memory", return_value=None):
        result = await engine.apply_sync(mock_session, mock_adapter, change)

    assert result is True
    mock_adapter.write_note.assert_not_called()


@pytest.mark.asyncio
async def test_apply_sync_updated_openbrain_wins_writes_obsidian():
    """apply_sync UPDATED with openbrain resolution must overwrite the Obsidian note."""
    from src.obsidian_sync import BidirectionalSyncEngine

    engine = BidirectionalSyncEngine()
    mock_session = AsyncMock()
    mock_adapter = AsyncMock()
    mock_adapter.write_note = AsyncMock(
        return_value=_written_note("Memory/conflict-note.md", "authoritative")
    )
    change = _make_conflict_change()
    mem = _make_memory("mem-99")

    with patch.object(engine, "resolve_conflict", return_value="openbrain"):
        with patch("src.memory_reads.get_memory", return_value=mem):
            with patch(
                "src.services.converter.memory_to_note_content", return_value="# auth"
            ):
                with patch(
                    "src.services.converter.memory_to_frontmatter", return_value={}
                ):
                    result = await engine.apply_sync(mock_session, mock_adapter, change)

    assert result is True
    mock_adapter.write_note.assert_called_once()
    call_kwargs = mock_adapter.write_note.call_args[1]
    assert call_kwargs["overwrite"] is True


@pytest.mark.asyncio
async def test_apply_sync_updated_openbrain_wins_updates_tracker():
    """apply_sync UPDATED openbrain-wins must record updated sync state."""
    from src.obsidian_sync import BidirectionalSyncEngine

    engine = BidirectionalSyncEngine()
    mock_session = AsyncMock()
    mock_adapter = AsyncMock()
    mock_adapter.write_note = AsyncMock(
        return_value=_written_note("Memory/conflict-note.md", "authoritative")
    )
    change = _make_conflict_change()

    with patch.object(engine, "resolve_conflict", return_value="openbrain"):
        with patch("src.memory_reads.get_memory", return_value=_make_memory("mem-99")):
            with patch(
                "src.services.converter.memory_to_note_content", return_value="# auth"
            ):
                with patch(
                    "src.services.converter.memory_to_frontmatter", return_value={}
                ):
                    with patch.object(engine.tracker, "update_state") as mock_state:
                        await engine.apply_sync(mock_session, mock_adapter, change)

    mock_state.assert_called_once()
