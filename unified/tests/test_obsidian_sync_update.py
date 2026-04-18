"""Tests for BidirectionalSyncEngine._update_memory_from_obsidian."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_change(memory_id: str = "mem-123"):
    from src.obsidian_sync import SyncChange, ChangeType

    return SyncChange(
        change_type=ChangeType.UPDATED,
        source="obsidian",
        memory_id=memory_id,
        obsidian_path="Memory/my-note.md",
        vault="MyVault",
    )


def _make_note():
    note = MagicMock()
    note.content = "Updated content from Obsidian"
    note.frontmatter = {"title": "My Note"}
    note.tags = ["tag1"]
    note.path = "Memory/my-note.md"
    return note


@pytest.mark.asyncio
async def test_update_memory_from_obsidian_calls_update_memory():
    """_update_memory_from_obsidian must persist updated content to DB via update_memory."""
    from src.obsidian_sync import BidirectionalSyncEngine

    engine = BidirectionalSyncEngine()
    mock_session = AsyncMock()
    mock_adapter = AsyncMock()
    mock_adapter.read_note = AsyncMock(return_value=_make_note())
    change = _make_change(memory_id="mem-123")

    with patch("src.memory_writes.update_memory") as mock_update:
        mock_update.return_value = MagicMock()
        await engine._update_memory_from_obsidian(mock_session, mock_adapter, change)

    mock_update.assert_called_once()
    # First positional arg is session, second is memory_id
    call_args = mock_update.call_args
    assert call_args[0][1] == "mem-123"


@pytest.mark.asyncio
async def test_update_memory_from_obsidian_passes_content():
    """_update_memory_from_obsidian must pass the note content to update_memory."""
    from src.obsidian_sync import BidirectionalSyncEngine
    from src.schemas import MemoryUpdate

    engine = BidirectionalSyncEngine()
    mock_session = AsyncMock()
    mock_adapter = AsyncMock()
    note = _make_note()
    mock_adapter.read_note = AsyncMock(return_value=note)
    change = _make_change()

    with patch("src.memory_writes.update_memory") as mock_update:
        mock_update.return_value = MagicMock()
        await engine._update_memory_from_obsidian(mock_session, mock_adapter, change)

    call_args = mock_update.call_args
    data: MemoryUpdate = call_args[0][2]
    assert data.content == "Updated content from Obsidian"


@pytest.mark.asyncio
async def test_update_memory_from_obsidian_empty_memory_id_raises():
    """_update_memory_from_obsidian must raise ObsidianCliError when memory_id is empty."""
    from src.obsidian_sync import BidirectionalSyncEngine
    from src.exceptions import ObsidianCliError

    engine = BidirectionalSyncEngine()
    mock_session = AsyncMock()
    mock_adapter = AsyncMock()
    change = _make_change(memory_id="")  # empty string = CREATED change with no id

    with pytest.raises(ObsidianCliError, match="memory_id"):
        await engine._update_memory_from_obsidian(mock_session, mock_adapter, change)
