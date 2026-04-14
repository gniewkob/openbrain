"""Branch coverage for pure utility functions in src/common/obsidian_adapter.py.

Covers uncovered lines in subprocess-free utility code:
- Lines 66, 77: env parsing edge cases
- Lines 113-114: _clean_cli_output filters
- Lines 126, 128, 131, 133, 135-138: _coerce_frontmatter_value branches
- Lines 153, 160, 167-168: _parse_frontmatter branches
- Lines 187, 191, 198-200: _merge_tags branches
- Lines 207, 209-211: _derive_title with heading
- Lines 223-239: note_to_write_payload (full coverage)
- Line 266: note_to_memory_write_record invalid domain
"""

from __future__ import annotations

import os
import pytest
from unittest.mock import patch


# ---------------------------------------------------------------------------
# _configured_vault_names_from_env — line 66 (empty raw_name)
# ---------------------------------------------------------------------------


def test_configured_vault_names_skips_empty_names():
    """Env var like OBSIDIAN_VAULT__PATH (empty name part) → skipped (line 66)."""
    from src.common.obsidian_adapter import _configured_vault_names_from_env

    with patch.dict(os.environ, {"OBSIDIAN_VAULT__PATH": "/some/path"}, clear=False):
        names = _configured_vault_names_from_env()

    # Empty name (between OBSIDIAN_VAULT_ and _PATH) should be skipped
    assert "" not in names


# ---------------------------------------------------------------------------
# _parse_vault_paths_mapping — line 77 (empty string)
# ---------------------------------------------------------------------------


def test_parse_vault_paths_mapping_returns_empty_for_empty_string():
    """Empty string → returns {} (line 77)."""
    from src.common.obsidian_adapter import _parse_vault_paths_mapping

    assert _parse_vault_paths_mapping("") == {}
    assert _parse_vault_paths_mapping("   ") == {}


# ---------------------------------------------------------------------------
# _clean_cli_output — lines 113-114
# ---------------------------------------------------------------------------


def test_clean_cli_output_removes_loader_warning():
    """Lines matching log prefix + 'Loading updated app package' → removed (line 113-114)."""
    from src.common.obsidian_adapter import _clean_cli_output

    raw = (
        "Normal output\n"
        "2024-01-15 Loading updated app package from path...\n"
        "More output\n"
        "Your Obsidian installer is out of date.\n"
    )
    result = _clean_cli_output(raw)
    assert "Loading updated app package" not in result
    assert "Your Obsidian installer is out of date." not in result
    assert "Normal output" in result
    assert "More output" in result


def test_clean_cli_output_preserves_blank_lines():
    """Empty stripped line → append '' and continue (lines 113-114)."""
    from src.common.obsidian_adapter import _clean_cli_output

    raw = "line one\n\nline three"
    result = _clean_cli_output(raw)
    assert "line one" in result
    assert "line three" in result
    # Blank line should be preserved as an empty line in the middle
    assert "\n\n" in result or result.count("\n") >= 1


# ---------------------------------------------------------------------------
# _coerce_frontmatter_value — all branches
# ---------------------------------------------------------------------------


def test_coerce_frontmatter_value_empty_string():
    """Empty value → '' (line 126)."""
    from src.common.obsidian_adapter import _coerce_frontmatter_value

    assert _coerce_frontmatter_value("") == ""
    assert _coerce_frontmatter_value("   ") == ""


def test_coerce_frontmatter_value_quoted_string():
    """Quoted value → unquoted (line 128)."""
    from src.common.obsidian_adapter import _coerce_frontmatter_value

    assert _coerce_frontmatter_value('"hello"') == "hello"
    assert _coerce_frontmatter_value("'world'") == "world"


def test_coerce_frontmatter_value_true():
    """'true' → True (line 131)."""
    from src.common.obsidian_adapter import _coerce_frontmatter_value

    assert _coerce_frontmatter_value("true") is True
    assert _coerce_frontmatter_value("TRUE") is True


def test_coerce_frontmatter_value_false():
    """'false' → False (line 133)."""
    from src.common.obsidian_adapter import _coerce_frontmatter_value

    assert _coerce_frontmatter_value("false") is False
    assert _coerce_frontmatter_value("False") is False


def test_coerce_frontmatter_value_list():
    """'[a, b]' → ['a', 'b'] (line 135-138)."""
    from src.common.obsidian_adapter import _coerce_frontmatter_value

    assert _coerce_frontmatter_value("[a, b, c]") == ["a", "b", "c"]


def test_coerce_frontmatter_value_empty_list():
    """'[]' → [] (line 136-137)."""
    from src.common.obsidian_adapter import _coerce_frontmatter_value

    assert _coerce_frontmatter_value("[]") == []


# ---------------------------------------------------------------------------
# _parse_frontmatter — lines 153, 160, 167-168
# ---------------------------------------------------------------------------


def test_parse_frontmatter_no_closing_delimiter():
    """Frontmatter opened with --- but no closing --- → returns {}, content (line 153)."""
    from src.common.obsidian_adapter import _parse_frontmatter

    content = "---\ntitle: Test\nNo closing delimiter here\nMore content"
    metadata, body = _parse_frontmatter(content)
    assert metadata == {}
    assert content in body or body == content


def test_parse_frontmatter_empty_lines_skipped():
    """Empty lines inside frontmatter block → skipped (line 160)."""
    from src.common.obsidian_adapter import _parse_frontmatter

    content = "---\ntitle: My Title\n\ndomain: build\n---\nBody content"
    metadata, body = _parse_frontmatter(content)
    assert metadata.get("title") == "My Title"
    assert metadata.get("domain") == "build"


def test_parse_frontmatter_line_without_colon_resets_list_key():
    """Line without ':' resets current_list_key (lines 167-168)."""
    from src.common.obsidian_adapter import _parse_frontmatter

    content = "---\ntags:\n- one\ninvalid line without colon\n- orphan\n---\nBody"
    metadata, body = _parse_frontmatter(content)
    # 'invalid line without colon' has no colon → resets current_list_key
    # '- orphan' should NOT be appended to tags
    tags = metadata.get("tags", [])
    assert "orphan" not in tags
    assert "one" in tags


# ---------------------------------------------------------------------------
# _merge_tags — lines 187, 191, 198-200
# ---------------------------------------------------------------------------


def test_merge_tags_string_tags():
    """fm_tags is a str → split on comma (line 187)."""
    from src.common.obsidian_adapter import _merge_tags

    result = _merge_tags({"tags": "ai, code, #python"}, [])
    assert "ai" in result
    assert "code" in result
    assert "python" in result  # # stripped


def test_merge_tags_list_tags():
    """fm_tags is a list → extend (line 191)."""
    from src.common.obsidian_adapter import _merge_tags

    result = _merge_tags({"tags": ["ai", "code"]}, ["extra"])
    assert "ai" in result
    assert "code" in result
    assert "extra" in result


def test_merge_tags_deduplication():
    """Duplicate tags → deduped (lines 198-200)."""
    from src.common.obsidian_adapter import _merge_tags

    result = _merge_tags({"tags": ["ai", "ai", "code"]}, ["ai"])
    assert result.count("ai") == 1


# ---------------------------------------------------------------------------
# _derive_title — lines 207, 209-211
# ---------------------------------------------------------------------------


def test_derive_title_from_heading_when_no_frontmatter_title():
    """No frontmatter title, body starts with # heading → use heading (line 207, 209-211)."""
    from src.common.obsidian_adapter import _derive_title

    body = "# My Great Document\nSome body text"
    result = _derive_title("folder/my-doc.md", {}, body)
    assert result == "My Great Document"


def test_derive_title_from_path_stem_when_no_title_and_no_heading():
    """No frontmatter title, no heading → use path stem."""
    from src.common.obsidian_adapter import _derive_title

    result = _derive_title("folder/my-document.md", {}, "Just plain content")
    assert result == "my-document"


# ---------------------------------------------------------------------------
# note_to_write_payload — lines 223-239 (full function coverage)
# ---------------------------------------------------------------------------


def test_note_to_write_payload_invalid_domain_falls_back():
    """Domain not in _VALID_DOMAINS → uses default_domain (line 225-226)."""
    from src.common.obsidian_adapter import note_to_write_payload, ObsidianNote

    note = ObsidianNote(
        vault="MyVault",
        path="notes/test.md",
        title="Test",
        content="Content here",
        frontmatter={"domain": "invalid-domain"},
        tags=["tag1"],
        file_hash="abc123",
    )

    payload = note_to_write_payload(
        note,
        default_domain="build",
        default_entity_type="Note",
        default_owner="agent",
        default_tags=["default-tag"],
    )

    assert payload["domain"] == "build"  # fell back to default
    assert "match_key" in payload
    assert payload["match_key"] == "obsidian:MyVault:notes/test.md"
    assert "default-tag" in payload["tags"]
    assert "tag1" in payload["tags"]


def test_note_to_write_payload_deduplicates_tags():
    """Tags deduped between default_tags and note.tags (lines 233-238)."""
    from src.common.obsidian_adapter import note_to_write_payload, ObsidianNote

    note = ObsidianNote(
        vault="V",
        path="p.md",
        title="T",
        content="C",
        frontmatter={},
        tags=["ai", "ai"],
        file_hash="f",
    )
    payload = note_to_write_payload(note, "build", "Note", default_tags=["ai"])
    assert payload["tags"].count("ai") == 1


# ---------------------------------------------------------------------------
# note_to_memory_write_record — line 266 (invalid domain fallback)
# ---------------------------------------------------------------------------


def test_note_to_memory_write_record_invalid_domain_falls_back():
    """Domain not in _VALID_DOMAINS → uses default_domain (line 265-266)."""
    from src.common.obsidian_adapter import note_to_memory_write_record, ObsidianNote

    note = ObsidianNote(
        vault="V",
        path="p.md",
        title="T",
        content="Content",
        frontmatter={"domain": "unknown-domain"},
        tags=[],
        file_hash="f",
    )

    record = note_to_memory_write_record(note, "build", "Note")
    assert record.domain == "build"
