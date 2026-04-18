"""Tests for MemoryOut.title property (custom_fields accessor)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest


def _make_memory_out(**overrides):
    from src.schemas import MemoryOut

    defaults = dict(
        id="test-id-123",
        domain="build",
        entity_type="Note",
        content="Test content",
        owner="tester",
        status="active",
        version=1,
        sensitivity="internal",
        tags=[],
        relations={},
        custom_fields={},
        content_hash="abc",
        created_by="tester",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    defaults.update(overrides)
    return MemoryOut(**defaults)


def test_memory_out_title_none_when_not_in_custom_fields():
    """MemoryOut.title must return None when custom_fields has no 'title'."""
    mem = _make_memory_out()
    assert mem.title is None


def test_memory_out_title_from_custom_fields():
    """MemoryOut.title must return the value from custom_fields['title']."""
    mem = _make_memory_out(custom_fields={"title": "My Note"})
    assert mem.title == "My Note"


def test_memory_out_title_returns_string():
    """MemoryOut.title must coerce non-string values to str."""
    mem = _make_memory_out(custom_fields={"title": 42})
    assert mem.title == "42"


def test_memory_out_title_empty_string_treated_as_none():
    """MemoryOut.title must return None for empty string titles."""
    mem = _make_memory_out(custom_fields={"title": ""})
    assert mem.title is None


def test_memory_out_title_included_in_model_dump():
    """MemoryOut.title must appear in model_dump() output (computed_field, not bare @property)."""
    mem = _make_memory_out(custom_fields={"title": "My Title"})
    dumped = mem.model_dump()
    assert "title" in dumped
    assert dumped["title"] == "My Title"
