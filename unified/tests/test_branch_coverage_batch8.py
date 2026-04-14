"""Batch 8 branch coverage for small remaining gaps.

Covers:
- src/db.py lines 29-30: _uses_dev_database_credentials exception → False
- src/schemas.py line 81: custom_fields key not str → ValueError
- src/obsidian_sync.py line 685: obsidian-wins path `pass` (read note succeeds)
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# db.py lines 29-30 — urlsplit exception → returns False
# ---------------------------------------------------------------------------


def test_uses_dev_database_credentials_exception_returns_false():
    """urlsplit raises → returns False (lines 29-30)."""
    from src.db import _uses_dev_database_credentials

    with patch("src.db.urlsplit", side_effect=Exception("parse error")):
        result = _uses_dev_database_credentials("some-bad-url://credentials")

    assert result is False


# ---------------------------------------------------------------------------
# schemas.py line 81 — custom_fields key not str → ValueError
# ---------------------------------------------------------------------------


def test_custom_fields_non_str_key_raises():
    """custom_fields with non-str key → ValueError (line 81)."""
    from src.schemas import MemoryWriteRecord
    import pytest

    with pytest.raises(Exception):  # ValidationError wraps ValueError
        MemoryWriteRecord(
            content="test",
            domain="build",
            entity_type="Note",
            custom_fields={123: "value"},  # int key, not str
        )


# ---------------------------------------------------------------------------
# obsidian_sync.py line 685 — obsidian-wins path: read_note succeeds, `pass`
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_apply_sync_updated_obsidian_wins_read_succeeds():
    """obsidian wins + adapter.read_note succeeds → hits pass at line 685, returns True."""
    from src.obsidian_sync import BidirectionalSyncEngine, SyncStrategy, SyncChange, ChangeType

    engine = BidirectionalSyncEngine(strategy=SyncStrategy.DOMAIN_BASED)

    change = SyncChange(
        memory_id="m1",
        obsidian_path="note.md",
        vault="vault",
        change_type=ChangeType.UPDATED,
        source="obsidian",
        conflict=False,
    )

    mock_note = MagicMock()
    mock_note.content = "updated content"
    mock_note.path = "note.md"

    mock_adapter = AsyncMock()
    mock_adapter.read_note = AsyncMock(return_value=mock_note)
    mock_session = AsyncMock()

    # resolve_conflict returns "obsidian" → takes the obsidian-wins path
    # read_note succeeds → hits line 685 `pass`, returns True (line 705)
    with patch.object(engine, "resolve_conflict", return_value="obsidian"):
        result = await engine.apply_sync(mock_session, mock_adapter, change)

    assert result is True
