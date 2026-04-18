"""Batch 5 branch coverage for remaining small gaps.

Covers:
- src/models.py lines 37, 41: _now() and _uuid() helper functions
- src/crud_common.py line 273: _match_metadata_fields function body
- src/repositories/memory_repository.py lines 313-316: match_key reindex in update
- src/api/v1/obsidian.py line 432: frontmatter tags branch in update-note
- src/api/v1/obsidian.py lines 73-81: _get_sync_engine double-checked lock
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# src/models.py lines 37, 41 — _now() and _uuid() column defaults
# ---------------------------------------------------------------------------


def test_models_now_returns_datetime():
    """_now() returns a timezone-aware datetime (line 37)."""
    from datetime import datetime, timezone
    from src.models import _now

    result = _now()
    assert isinstance(result, datetime)
    assert result.tzinfo is not None


def test_models_uuid_returns_string():
    """_uuid() returns a UUID string (line 41)."""
    from src.models import _uuid

    result = _uuid()
    assert isinstance(result, str)
    assert len(result) == 36  # standard UUID format


# ---------------------------------------------------------------------------
# src/crud_common.py line 273 — _match_metadata_fields function
# ---------------------------------------------------------------------------


def test_match_metadata_fields_returns_true_when_all_match():
    """_match_metadata_fields returns True when metadata matches record (line 273)."""
    from src.crud_common import _match_metadata_fields

    source_data = {"url": "https://example.com"}
    existing = MagicMock()  # not used in the function

    rec = MagicMock()
    rec.title = "My Title"
    rec.custom_fields = {"key": "value"}
    rec.source.model_dump.return_value = source_data

    metadata = {
        "title": "My Title",
        "custom_fields": {"key": "value"},
        "source": source_data,
    }

    result = _match_metadata_fields(existing, rec, metadata)
    assert result is True


def test_match_metadata_fields_returns_false_on_title_mismatch():
    """_match_metadata_fields returns False when title differs (line 273)."""
    from src.crud_common import _match_metadata_fields

    existing = MagicMock()
    rec = MagicMock()
    rec.title = "Different Title"
    rec.custom_fields = {}
    rec.source.model_dump.return_value = {}

    metadata = {"title": "Original Title", "custom_fields": None, "source": None}

    result = _match_metadata_fields(existing, rec, metadata)
    assert result is False


# ---------------------------------------------------------------------------
# src/repositories/memory_repository.py lines 313-316 — match_key reindex
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_rewrites_match_key_index():
    """update() with new match_key rewrites _match_key_index (lines 313-316)."""
    from src.repositories.memory_repository import InMemoryMemoryRepository

    repo = InMemoryMemoryRepository()
    mem = MagicMock()
    mem.id = "mem_1"
    mem.match_key = "old-key"
    repo.seed([mem])

    # Pre-condition: old-key is in the index
    assert repo._match_key_index.get("old-key") == "mem_1"

    # Mock update data to include match_key change
    mock_data = MagicMock()
    mock_data.model_dump.return_value = {"match_key": "new-key"}

    await repo.update("mem_1", mock_data)

    # old-key removed, new-key added
    assert "old-key" not in repo._match_key_index
    assert repo._match_key_index.get("new-key") == "mem_1"


# ---------------------------------------------------------------------------
# src/api/v1/obsidian.py line 432 — frontmatter tags branch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_v1_obsidian_update_note_with_tags_sets_frontmatter():
    """POST /update-note with tags → frontmatter = {"tags": tags} (line 432)."""
    import src.api.v1.obsidian as obs_mod

    mock_note = MagicMock()
    mock_note.vault = "v"
    mock_note.path = "p"
    mock_note.title = "t"
    mock_note.content = "c"
    mock_note.frontmatter = {"tags": ["ai"]}
    mock_note.tags = ["ai"]
    mock_note.file_hash = "hash123"

    with patch("src.api.v1.obsidian.ObsidianCliAdapter") as mock_cls:
        mock_adapter = AsyncMock()
        mock_adapter.update_note = AsyncMock(return_value=mock_note)
        mock_cls.return_value = mock_adapter

        await obs_mod.v1_obsidian_update_note(
            vault="v",
            path="p",
            content="c",
            append=False,
            tags=["ai"],
            _user={"sub": "test"},
        )

    # frontmatter was set with tags (line 432 executed)
    call_kwargs = mock_adapter.update_note.call_args[1]
    assert call_kwargs["frontmatter"] == {"tags": ["ai"]}


# ---------------------------------------------------------------------------
# src/api/v1/obsidian.py lines 73-81 — _get_sync_engine singleton creation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_sync_engine_creates_singleton():
    """_get_sync_engine with None engine → creates and caches engine (lines 73-81)."""
    import src.api.v1.obsidian as obsidian_mod

    original_engine = obsidian_mod._sync_engine
    try:
        obsidian_mod._sync_engine = None

        mock_tracker = AsyncMock()
        mock_engine_instance = MagicMock()

        with (
            patch.object(
                obsidian_mod, "_get_sync_tracker", AsyncMock(return_value=mock_tracker)
            ),
        ):
            with patch("src.api.v1.obsidian.BidirectionalSyncEngine") as mock_cls:
                mock_cls.return_value = mock_engine_instance
                engine = await obsidian_mod._get_sync_engine("domain_based")

        # Engine was created (lines 73-81 executed)
        assert engine is not None
    finally:
        obsidian_mod._sync_engine = original_engine
