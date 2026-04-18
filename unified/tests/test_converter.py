"""Tests for src/services/converter.py — memory ↔ Obsidian note format."""

from datetime import datetime, timezone

from unittest.mock import MagicMock

from src.schemas import ObsidianExportItem
from src.services.converter import (
    build_collection_index,
    memory_to_frontmatter,
    memory_to_note_content,
    sanitize_filename,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
# MemoryOut has no `title` field; the converter is duck-typed. Use MagicMock.

_NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)


def _memory(**kwargs):
    """Return a MagicMock mimicking the attributes converter.py accesses."""
    mem = MagicMock()
    mem.id = kwargs.get("id", "mem-1")
    mem.domain = kwargs.get("domain", "build")
    mem.entity_type = kwargs.get("entity_type", "Note")
    mem.content = kwargs.get("content", "Test content")
    mem.owner = kwargs.get("owner", "alice")
    mem.status = kwargs.get("status", "active")
    mem.version = kwargs.get("version", 1)
    mem.title = kwargs.get("title", None)
    mem.tags = kwargs.get("tags", [])
    mem.created_at = kwargs.get("created_at", _NOW)
    mem.updated_at = kwargs.get("updated_at", _NOW)
    return mem


def _export_item(
    memory_id="mem-1", path="Notes/note.md", title="Note"
) -> ObsidianExportItem:
    return ObsidianExportItem(memory_id=memory_id, path=path, title=title, created=True)


# ---------------------------------------------------------------------------
# sanitize_filename
# ---------------------------------------------------------------------------


def test_sanitize_removes_unsafe_chars():
    assert sanitize_filename('file<>:"/\\|?*.txt') == "file_________.txt"


def test_sanitize_limits_length():
    assert len(sanitize_filename("x" * 200)) == 100


def test_sanitize_clean_name_unchanged():
    assert sanitize_filename("clean-name_123") == "clean-name_123"


# ---------------------------------------------------------------------------
# memory_to_note_content — default format
# ---------------------------------------------------------------------------


def test_note_content_default_includes_title():
    mem = _memory(title="My Note")
    content = memory_to_note_content(mem)
    assert "# My Note" in content


def test_note_content_default_untitled_when_no_title():
    mem = _memory()
    content = memory_to_note_content(mem)
    assert "# Untitled" in content


def test_note_content_default_includes_domain_and_type():
    mem = _memory()
    content = memory_to_note_content(mem)
    assert "build" in content
    assert "Note" in content


def test_note_content_default_includes_body():
    mem = _memory(content="Hello world")
    content = memory_to_note_content(mem)
    assert "Hello world" in content


def test_note_content_default_includes_id_and_version():
    mem = _memory()
    content = memory_to_note_content(mem)
    assert "mem-1" in content
    assert "Version: 1" in content


def test_note_content_with_tags():
    mem = _memory(tags=["python", "backend"])
    content = memory_to_note_content(mem)
    assert "python" in content
    assert "backend" in content


# ---------------------------------------------------------------------------
# memory_to_note_content — with template
# ---------------------------------------------------------------------------


def test_note_content_template_used():
    mem = _memory(title="T")
    tmpl = "TITLE={title} CONTENT={content}"
    result = memory_to_note_content(mem, template=tmpl)
    assert result == "TITLE=T CONTENT=Test content"


def test_note_content_template_fallback_on_bad_template():
    mem = _memory()
    result = memory_to_note_content(mem, template="{nonexistent_key}")
    # Falls back to default format
    assert "# Untitled" in result


# ---------------------------------------------------------------------------
# memory_to_frontmatter
# ---------------------------------------------------------------------------


def test_frontmatter_has_required_keys():
    mem = _memory()
    fm = memory_to_frontmatter(mem)
    for key in (
        "openbrain_id",
        "domain",
        "entity_type",
        "owner",
        "version",
        "status",
        "tags",
    ):
        assert key in fm


def test_frontmatter_created_at_is_iso_string():
    mem = _memory()
    fm = memory_to_frontmatter(mem)
    assert isinstance(fm["created_at"], str)
    assert "2026" in fm["created_at"]


def test_frontmatter_updated_at_fallback_to_str():
    mem = _memory()
    # Simulate an object that has no isoformat (covered by str() branch)
    mem.updated_at = "not-a-datetime"  # type: ignore[assignment]
    fm = memory_to_frontmatter(mem)
    assert fm["updated_at"] == "not-a-datetime"


def test_frontmatter_source_is_openbrain_export():
    mem = _memory()
    fm = memory_to_frontmatter(mem)
    assert fm["source"] == "openbrain-export"


# ---------------------------------------------------------------------------
# build_collection_index — no grouping
# ---------------------------------------------------------------------------


def test_collection_index_no_grouping_lists_items():
    exported = [
        _export_item("m1", "Notes/a.md", "Alpha"),
        _export_item("m2", "Notes/b.md", "Beta"),
    ]
    result = build_collection_index("MyCol", "test query", exported, [], None)
    assert "MyCol" in result
    assert "Alpha" in result
    assert "Beta" in result
    assert "2 items" in result


def test_collection_index_no_grouping_strips_md_extension():
    exported = [_export_item("m1", "Notes/a.md", "A")]
    result = build_collection_index("C", "q", exported, [], None)
    assert "[[Notes/a]]" in result


# ---------------------------------------------------------------------------
# build_collection_index — with grouping
# ---------------------------------------------------------------------------


def test_collection_index_group_by_entity_type():
    mems = [_memory(id="m1", entity_type="Note"), _memory(id="m2", entity_type="Fact")]
    exported = [_export_item("m1", "a.md", "A"), _export_item("m2", "b.md", "B")]
    result = build_collection_index("C", "q", exported, mems, "entity_type")
    assert "### Note" in result
    assert "### Fact" in result


def test_collection_index_group_by_owner():
    mems = [_memory(id="m1", owner="alice"), _memory(id="m2", owner="bob")]
    exported = [_export_item("m1", "a.md", "A"), _export_item("m2", "b.md", "B")]
    result = build_collection_index("C", "q", exported, mems, "owner")
    assert "### alice" in result
    assert "### bob" in result


def test_collection_index_group_by_tags_first_tag():
    mems = [_memory(id="m1", tags=["python"]), _memory(id="m2", tags=[])]
    exported = [_export_item("m1", "a.md", "A"), _export_item("m2", "b.md", "B")]
    result = build_collection_index("C", "q", exported, mems, "tags")
    assert "### python" in result
    assert "### Untagged" in result


def test_collection_index_group_by_unknown_key():
    mems = [_memory(id="m1")]
    exported = [_export_item("m1", "a.md", "A")]
    result = build_collection_index("C", "q", exported, mems, "unknown_field")
    assert "### Other" in result


def test_collection_index_group_by_skipped_when_memory_not_found():
    mems = [_memory(id="other")]
    exported = [_export_item("m1", "a.md", "A")]
    result = build_collection_index("C", "q", exported, mems, "entity_type")
    # m1 not in mems → skipped, no section headers
    assert "###" not in result
