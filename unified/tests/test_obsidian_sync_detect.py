"""Tests for BidirectionalSyncEngine.detect_changes — Obsidian change detection."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_state(path: str = "Memory/note.md", content_hash: str = "oldhash"):
    from src.obsidian_sync import SyncState

    return SyncState(
        memory_id="mem-1",
        obsidian_path=path,
        vault="TestVault",
        content_hash=content_hash,
        memory_updated_at=datetime.now(timezone.utc),
        obsidian_modified_at=datetime.now(timezone.utc),
    )


def _make_engine(states):
    from src.obsidian_sync import BidirectionalSyncEngine, ObsidianChangeTracker

    tracker = MagicMock(spec=ObsidianChangeTracker)
    tracker.get_all_states.return_value = states
    engine = BidirectionalSyncEngine(tracker=tracker)
    return engine


@pytest.mark.asyncio
async def test_detect_changes_obsidian_updated_when_hash_differs():
    """detect_changes must emit UPDATED(source=obsidian) when note hash changed."""
    from src.obsidian_sync import ChangeType

    state = _make_state(content_hash="aabbccdd")
    engine = _make_engine([state])

    mock_session = AsyncMock()
    mock_adapter = AsyncMock()
    mock_adapter.list_files = AsyncMock(return_value=["Memory/note.md"])
    changed_note = MagicMock()
    changed_note.content = "brand new content"
    mock_adapter.read_note = AsyncMock(return_value=changed_note)

    with patch("src.obsidian_sync._get_openbrain_memories", return_value={}):
        changes = await engine.detect_changes(mock_session, mock_adapter, "TestVault")

    updated = [c for c in changes if c.memory_id == "mem-1"]
    assert len(updated) == 1
    assert updated[0].change_type == ChangeType.UPDATED
    assert updated[0].source == "obsidian"


@pytest.mark.asyncio
async def test_detect_changes_no_change_when_hash_same():
    """detect_changes must not emit a change when note content is unchanged."""
    from src.obsidian_sync import BidirectionalSyncEngine

    # Compute the real hash so it matches what detect_changes will compute
    hash_val = BidirectionalSyncEngine.compute_content_hash("same content")
    state = _make_state(content_hash=hash_val)
    engine = _make_engine([state])

    mock_session = AsyncMock()
    mock_adapter = AsyncMock()
    mock_adapter.list_files = AsyncMock(return_value=["Memory/note.md"])
    unchanged_note = MagicMock()
    unchanged_note.content = "same content"
    mock_adapter.read_note = AsyncMock(return_value=unchanged_note)

    with patch("src.obsidian_sync._get_openbrain_memories", return_value={}):
        changes = await engine.detect_changes(mock_session, mock_adapter, "TestVault")

    updated = [c for c in changes if c.memory_id == "mem-1" and c.source == "obsidian"]
    assert updated == []


@pytest.mark.asyncio
async def test_detect_changes_read_note_exception_treated_as_unchanged():
    """If read_note raises for a tracked path, it must be treated as unchanged (not crash)."""
    state = _make_state(content_hash="somehash")
    engine = _make_engine([state])

    mock_session = AsyncMock()
    mock_adapter = AsyncMock()
    mock_adapter.list_files = AsyncMock(return_value=["Memory/note.md"])
    mock_adapter.read_note = AsyncMock(side_effect=Exception("CLI failure"))

    with patch("src.obsidian_sync._get_openbrain_memories", return_value={}):
        changes = await engine.detect_changes(mock_session, mock_adapter, "TestVault")

    # Should not raise; the state should be treated as unchanged
    obsidian_updated = [
        c for c in changes if c.source == "obsidian" and c.memory_id == "mem-1"
    ]
    assert obsidian_updated == []
