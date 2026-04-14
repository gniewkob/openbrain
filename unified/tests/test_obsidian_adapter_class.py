"""Branch coverage for ObsidianCliAdapter class in src/common/obsidian_adapter.py.

Covers:
- Lines 305-334: _run (FileNotFoundError, TimeoutError, non-zero exit, success)
- Lines 357, 361: _validate_vault_path (invalid vault, invalid path)
- Lines 375-393: list_files via filesystem
- Lines 398, 403: list_files CLI fallback with folder, limit
- Lines 415-461: read_note filesystem path (sync executor since no aiofiles)
- Lines 471-488: read_note CLI tag parsing (dict, other)
- Lines 548-557: write_note overwrite=False existing note
- Lines 565-566: note_exists → True
- Lines 572, 579-580, 585-588: _get_vault_path cache/env/mapping
- Lines 613-640: update_note branches
- Lines 659-689: delete_note branches
- Lines 701-740: _write_note_to_filesystem branches
- Line 748: _sync_write_file
- Lines 756-806: _build_note_content all value types

NOTE: conftest.py has a session-scoped autouse fixture that patches
ObsidianCliAdapter._run → AsyncMock(return_value="") globally.
To test the real _run we save the original at module-import time (before
the session fixture replaces it) and restore it per-test via patch.object.
"""

from __future__ import annotations

import asyncio
import os
import types
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Save the REAL _run before the session-scoped conftest patches it.
# Module import happens before session fixtures run in pytest.
# ---------------------------------------------------------------------------
import src.common.obsidian_adapter as _adapter_mod

_REAL_RUN = _adapter_mod.ObsidianCliAdapter._run  # unbound function, captured early


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_adapter(command: str = "/usr/bin/obsidian-cli") -> _adapter_mod.ObsidianCliAdapter:
    return _adapter_mod.ObsidianCliAdapter(command=command)


def _with_real_run(adapter):
    """Context manager: restore the real _run on this instance, bypassing the conftest patch."""
    return patch.object(adapter, "_run", new=types.MethodType(_REAL_RUN, adapter))


def _clear_vault_cache():
    _adapter_mod._VAULT_PATHS_CACHE.clear()


# ---------------------------------------------------------------------------
# _run — lines 305-334
# ---------------------------------------------------------------------------

class TestRun:
    @pytest.mark.asyncio
    async def test_run_file_not_found_raises(self):
        """FileNotFoundError → ObsidianCliError (lines 312-317)."""
        ObsidianCliError = _adapter_mod.ObsidianCliError
        adapter = _make_adapter()
        with _with_real_run(adapter):
            with patch(
                "src.common.obsidian_adapter.asyncio.create_subprocess_exec",
                new=AsyncMock(side_effect=FileNotFoundError("no cmd")),
            ):
                with pytest.raises(ObsidianCliError, match="not found"):
                    await adapter._run("vaults")

    @pytest.mark.asyncio
    async def test_run_timeout_kills_process(self):
        """TimeoutError → process.kill() → ObsidianCliError (lines 322-327)."""
        ObsidianCliError = _adapter_mod.ObsidianCliError
        mock_proc = MagicMock()
        mock_proc.returncode = None
        mock_proc.kill = MagicMock()
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))

        adapter = _make_adapter()
        adapter.timeout_s = 1.0
        with _with_real_run(adapter):
            with patch(
                "src.common.obsidian_adapter.asyncio.create_subprocess_exec",
                new=AsyncMock(return_value=mock_proc),
            ):
                with patch(
                    "src.common.obsidian_adapter.asyncio.wait_for",
                    new=AsyncMock(side_effect=asyncio.TimeoutError()),
                ):
                    with pytest.raises(ObsidianCliError, match="timed out"):
                        await adapter._run("vaults")
        mock_proc.kill.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_nonzero_exit_raises(self):
        """Non-zero exit code → ObsidianCliError (lines 331-333)."""
        ObsidianCliError = _adapter_mod.ObsidianCliError
        mock_proc = MagicMock()
        mock_proc.returncode = 1

        adapter = _make_adapter()
        with _with_real_run(adapter):
            with patch(
                "src.common.obsidian_adapter.asyncio.create_subprocess_exec",
                new=AsyncMock(return_value=mock_proc),
            ):
                with patch(
                    "src.common.obsidian_adapter.asyncio.wait_for",
                    new=AsyncMock(return_value=(b"", b"some error")),
                ):
                    with pytest.raises(ObsidianCliError):
                        await adapter._run("vaults")

    @pytest.mark.asyncio
    async def test_run_success_returns_cleaned_stdout(self):
        """Successful run returns cleaned stdout (lines 329-334)."""
        mock_proc = MagicMock()
        mock_proc.returncode = 0

        adapter = _make_adapter()
        with _with_real_run(adapter):
            with patch(
                "src.common.obsidian_adapter.asyncio.create_subprocess_exec",
                new=AsyncMock(return_value=mock_proc),
            ):
                with patch(
                    "src.common.obsidian_adapter.asyncio.wait_for",
                    new=AsyncMock(return_value=(b"vault1\nvault2\n", b"")),
                ):
                    result = await adapter._run("vaults")
        assert "vault1" in result


# ---------------------------------------------------------------------------
# _validate_vault_path — lines 357, 361
# ---------------------------------------------------------------------------

class TestValidateVaultPath:
    def test_invalid_vault_slash_raises(self):
        """Vault name with slash → ObsidianCliError (line 357)."""
        adapter = _make_adapter()
        with pytest.raises(_adapter_mod.ObsidianCliError, match="Invalid vault name"):
            adapter._validate_vault_path("my/vault")

    def test_invalid_vault_dotdot_raises(self):
        """Vault name with '..' component → ObsidianCliError (line 357)."""
        adapter = _make_adapter()
        with pytest.raises(_adapter_mod.ObsidianCliError, match="Invalid vault name"):
            adapter._validate_vault_path("..")

    def test_invalid_path_dotdot_raises(self):
        """Note path with '..' → ObsidianCliError (line 361)."""
        adapter = _make_adapter()
        with pytest.raises(_adapter_mod.ObsidianCliError, match="Invalid note path"):
            adapter._validate_vault_path("myvault", "../escape.md")

    def test_invalid_path_absolute_raises(self):
        """Absolute note path → ObsidianCliError (line 361)."""
        adapter = _make_adapter()
        with pytest.raises(_adapter_mod.ObsidianCliError, match="Invalid note path"):
            adapter._validate_vault_path("myvault", "/absolute/path.md")

    def test_valid_vault_and_path(self):
        """Valid vault + path → no exception."""
        adapter = _make_adapter()
        adapter._validate_vault_path("myvault", "folder/note.md")


# ---------------------------------------------------------------------------
# _get_vault_path — lines 572, 579-580, 585-588
# ---------------------------------------------------------------------------

class TestGetVaultPath:
    @pytest.mark.asyncio
    async def test_get_vault_path_from_cache(self):
        """Cached value is returned immediately (line 572)."""
        _clear_vault_cache()
        _adapter_mod._VAULT_PATHS_CACHE["testvault"] = "/cached/path"
        adapter = _make_adapter()
        result = await adapter._get_vault_path("testvault")
        assert result == "/cached/path"
        _clear_vault_cache()

    @pytest.mark.asyncio
    async def test_get_vault_path_from_individual_env(self):
        """OBSIDIAN_VAULT_{NAME}_PATH env var (lines 579-580)."""
        _clear_vault_cache()
        adapter = _make_adapter()
        with patch.dict(os.environ, {"OBSIDIAN_VAULT_VAULTX_PATH": "/env/vaultx"}):
            result = await adapter._get_vault_path("vaultx")
        assert result == "/env/vaultx"
        _clear_vault_cache()

    @pytest.mark.asyncio
    async def test_get_vault_path_from_vault_paths_mapping(self):
        """OBSIDIAN_VAULT_PATHS aggregated mapping (lines 585-588)."""
        _clear_vault_cache()
        adapter = _make_adapter()
        # Use a vault name that has no individual env var
        clean_env = {
            k: v for k, v in os.environ.items()
            if "OBSIDIAN_VAULT_MAPV_PATH" not in k
        }
        clean_env["OBSIDIAN_VAULT_PATHS"] = "mapv:/tmp/mapv"
        with patch.dict(os.environ, clean_env, clear=True):
            result = await adapter._get_vault_path("mapv")
        assert result == "/tmp/mapv"
        _clear_vault_cache()

    @pytest.mark.asyncio
    async def test_get_vault_path_none_if_not_configured(self):
        """Returns None if vault not configured anywhere."""
        _clear_vault_cache()
        adapter = _make_adapter()
        clean_env = {
            k: v for k, v in os.environ.items()
            if "OBSIDIAN_VAULT_NOTEXIST" not in k and "OBSIDIAN_VAULT_PATHS" not in k
        }
        with patch.dict(os.environ, clean_env, clear=True):
            result = await adapter._get_vault_path("notexist")
        assert result is None
        _clear_vault_cache()


# ---------------------------------------------------------------------------
# list_files — lines 375-393, 398, 403
# ---------------------------------------------------------------------------

class TestListFiles:
    @pytest.mark.asyncio
    async def test_list_files_via_filesystem(self, tmp_path):
        """Filesystem path exists → returns .md files (lines 375-393)."""
        vault_dir = tmp_path / "vault"
        vault_dir.mkdir()
        (vault_dir / "note1.md").write_text("# Note 1")
        (vault_dir / "sub").mkdir()
        (vault_dir / "sub" / "note2.md").write_text("# Note 2")

        adapter = _make_adapter()
        with patch.object(adapter, "_get_vault_path", return_value=str(vault_dir)):
            result = await adapter.list_files("myvault")

        assert len(result) == 2
        assert any("note1.md" in r for r in result)

    @pytest.mark.asyncio
    async def test_list_files_with_limit(self, tmp_path):
        """limit parameter truncates results (line 403)."""
        vault_dir = tmp_path / "vault"
        vault_dir.mkdir()
        for i in range(5):
            (vault_dir / f"note{i}.md").write_text(f"# Note {i}")

        adapter = _make_adapter()
        with patch.object(adapter, "_get_vault_path", return_value=str(vault_dir)):
            result = await adapter.list_files("myvault", limit=2)

        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_list_files_via_filesystem_with_folder(self, tmp_path):
        """Filesystem + folder → lists only files under folder (line 377)."""
        vault_dir = tmp_path / "vault"
        vault_dir.mkdir()
        (vault_dir / "Projects").mkdir()
        (vault_dir / "Projects" / "note.md").write_text("# Project note")
        (vault_dir / "other.md").write_text("# Other")  # outside folder

        adapter = _make_adapter()
        with patch.object(adapter, "_get_vault_path", return_value=str(vault_dir)):
            result = await adapter.list_files("myvault", folder="Projects")

        assert any("note.md" in r for r in result)
        assert not any("other.md" in r for r in result)

    @pytest.mark.asyncio
    async def test_list_files_cli_fallback_with_folder(self):
        """No vault path → CLI fallback with folder arg (line 398)."""
        adapter = _make_adapter()
        with patch.object(adapter, "_get_vault_path", return_value=None):
            with patch.object(adapter, "_run", return_value="Projects/note.md\nProjects/other.md"):
                result = await adapter.list_files("myvault", folder="Projects")
        assert "Projects/note.md" in result

    @pytest.mark.asyncio
    async def test_list_files_filesystem_exception_falls_back_to_cli(self, tmp_path):
        """Exception during filesystem listing → CLI fallback (lines 391-403)."""
        vault_dir = tmp_path / "vault"
        vault_dir.mkdir()

        adapter = _make_adapter()
        with patch.object(adapter, "_get_vault_path", return_value=str(vault_dir)):
            with patch("pathlib.Path.rglob", side_effect=PermissionError("denied")):
                with patch.object(adapter, "_run", return_value="note.md"):
                    result = await adapter.list_files("myvault")
        assert "note.md" in result


# ---------------------------------------------------------------------------
# read_note — lines 415-461, 471-488
# (aiofiles not installed → sync executor path is the default)
# ---------------------------------------------------------------------------

class TestReadNote:
    @pytest.mark.asyncio
    async def test_read_note_via_sync_executor(self, tmp_path):
        """Read note via sync executor fallback (no aiofiles) (lines 440-458)."""
        vault_dir = tmp_path / "vault"
        vault_dir.mkdir()
        note_content = "---\ntitle: Test Note\n---\n# Hello\nBody text"
        (vault_dir / "note.md").write_text(note_content)

        adapter = _make_adapter()
        with patch.object(adapter, "_get_vault_path", return_value=str(vault_dir)):
            result = await adapter.read_note("myvault", "note.md")

        assert result.title == "Test Note"
        assert result.vault == "myvault"

    @pytest.mark.asyncio
    async def test_read_note_cli_no_vault_path(self):
        """No vault path → CLI path (lines 463-504)."""
        adapter = _make_adapter()
        note_content = "---\ntitle: CLI Note\n---\n# Body"
        tags_json = '["work", "project"]'
        with patch.object(adapter, "_get_vault_path", return_value=None):
            with patch.object(adapter, "_run", side_effect=[note_content, tags_json]):
                result = await adapter.read_note("myvault", "note.md")
        assert result.title == "CLI Note"
        assert "work" in result.tags

    @pytest.mark.asyncio
    async def test_read_note_cli_tags_dict_format(self):
        """CLI returns tags as dict → keys used as tags (lines 481-486)."""
        adapter = _make_adapter()
        with patch.object(adapter, "_get_vault_path", return_value=None):
            with patch.object(
                adapter, "_run",
                side_effect=["# Note\nbody", '{"tag1": null, "tag2": null}']
            ):
                result = await adapter.read_note("myvault", "note.md")
        assert "tag1" in result.tags
        assert "tag2" in result.tags

    @pytest.mark.asyncio
    async def test_read_note_cli_tags_other_format(self):
        """CLI returns tags as non-JSON lines → line-split parsing (lines 487-492)."""
        adapter = _make_adapter()
        with patch.object(adapter, "_get_vault_path", return_value=None):
            with patch.object(
                adapter, "_run",
                side_effect=["# Note\nbody", "not-json-at-all"]
            ):
                result = await adapter.read_note("myvault", "note.md")
        assert result.tags is not None

    @pytest.mark.asyncio
    async def test_read_note_cli_json_decode_error(self):
        """CLI tags with malformed JSON (not a list/dict) → fallback split (lines 473-492)."""
        adapter = _make_adapter()
        # '42' is valid JSON but not list/dict → falls to else: cli_tags from lines
        with patch.object(adapter, "_get_vault_path", return_value=None):
            with patch.object(
                adapter, "_run",
                side_effect=["# Note\nbody", "42"]
            ):
                result = await adapter.read_note("myvault", "note.md")
        # No tags from single-value JSON
        assert isinstance(result.tags, list)


# ---------------------------------------------------------------------------
# write_note — lines 548-557
# ---------------------------------------------------------------------------

class TestWriteNote:
    @pytest.mark.asyncio
    async def test_write_note_raises_if_exists_no_overwrite(self, tmp_path):
        """Note exists + overwrite=False → ObsidianCliError (lines 541-546)."""
        vault_dir = tmp_path / "vault"
        vault_dir.mkdir()
        (vault_dir / "existing.md").write_text("# Existing")

        adapter = _make_adapter()
        with patch.object(adapter, "_get_vault_path", return_value=str(vault_dir)):
            with pytest.raises(_adapter_mod.ObsidianCliError, match="already exists"):
                await adapter.write_note("myvault", "existing.md", "new content", overwrite=False)

    @pytest.mark.asyncio
    async def test_write_note_no_overwrite_new_file(self, tmp_path):
        """Note doesn't exist + overwrite=False → writes successfully (lines 547-557)."""
        vault_dir = tmp_path / "vault"
        vault_dir.mkdir()

        adapter = _make_adapter()
        # First read_note raises (file missing, CLI not found), second succeeds (file now exists)
        with patch.object(adapter, "_get_vault_path", return_value=str(vault_dir)):
            # _run is patched by conftest → returns "" → read_note won't find file in
            # CLI fallback (CLI returns empty content, treated as a valid note).
            # Fix: also mock _run to raise ObsidianCliError for the first read.
            ObsidianCliError = _adapter_mod.ObsidianCliError
            call_count = 0

            original_read = type(adapter).read_note

            async def read_note_side_effect(self, vault, path):
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    raise ObsidianCliError("File not found")
                return await original_read(self, vault, path)

            with patch.object(type(adapter), "read_note", new=read_note_side_effect):
                result = await adapter.write_note("myvault", "new.md", "# New content", overwrite=False)

        assert result.path == "new.md"
        assert (vault_dir / "new.md").exists()

    @pytest.mark.asyncio
    async def test_write_note_overwrite_true(self, tmp_path):
        """overwrite=True → skips existence check, writes directly."""
        vault_dir = tmp_path / "vault"
        vault_dir.mkdir()
        (vault_dir / "note.md").write_text("# Old")

        adapter = _make_adapter()
        with patch.object(adapter, "_get_vault_path", return_value=str(vault_dir)):
            result = await adapter.write_note("myvault", "note.md", "# Updated", overwrite=True)

        assert "Updated" in (vault_dir / "note.md").read_text()


# ---------------------------------------------------------------------------
# note_exists — lines 565-566
# ---------------------------------------------------------------------------

class TestNoteExists:
    @pytest.mark.asyncio
    async def test_note_exists_returns_true(self, tmp_path):
        """File present → read succeeds → True (lines 565-566)."""
        vault_dir = tmp_path / "vault"
        vault_dir.mkdir()
        (vault_dir / "note.md").write_text("# Note")

        adapter = _make_adapter()
        with patch.object(adapter, "_get_vault_path", return_value=str(vault_dir)):
            result = await adapter.note_exists("myvault", "note.md")
        assert result is True

    @pytest.mark.asyncio
    async def test_note_exists_returns_false(self):
        """read_note raises → False."""
        adapter = _make_adapter()
        with patch.object(adapter, "read_note", side_effect=_adapter_mod.ObsidianCliError("not found")):
            result = await adapter.note_exists("myvault", "missing.md")
        assert result is False


# ---------------------------------------------------------------------------
# update_note — lines 613-640
# ---------------------------------------------------------------------------

class TestUpdateNote:
    @pytest.mark.asyncio
    async def test_update_note_content_only(self, tmp_path):
        """content provided, no frontmatter → replaces content (lines 618-624)."""
        vault_dir = tmp_path / "vault"
        vault_dir.mkdir()
        (vault_dir / "note.md").write_text("# Old content")

        adapter = _make_adapter()
        with patch.object(adapter, "_get_vault_path", return_value=str(vault_dir)):
            await adapter.update_note("myvault", "note.md", content="# New content")

        assert "New content" in (vault_dir / "note.md").read_text()

    @pytest.mark.asyncio
    async def test_update_note_append_mode(self, tmp_path):
        """append=True → appends to existing content (line 622)."""
        vault_dir = tmp_path / "vault"
        vault_dir.mkdir()
        (vault_dir / "note.md").write_text("# Existing")

        adapter = _make_adapter()
        with patch.object(adapter, "_get_vault_path", return_value=str(vault_dir)):
            await adapter.update_note("myvault", "note.md", content="Appended", append=True)

        written = (vault_dir / "note.md").read_text()
        assert "Existing" in written
        assert "Appended" in written

    @pytest.mark.asyncio
    async def test_update_note_frontmatter_merged(self, tmp_path):
        """frontmatter provided → merged with existing + updated_at added (lines 627-633)."""
        vault_dir = tmp_path / "vault"
        vault_dir.mkdir()
        (vault_dir / "note.md").write_text("---\ntitle: Old Title\ntags: []\n---\n# Body")

        adapter = _make_adapter()
        with patch.object(adapter, "_get_vault_path", return_value=str(vault_dir)):
            await adapter.update_note("myvault", "note.md", frontmatter={"title": "New Title"})

        written = (vault_dir / "note.md").read_text()
        assert "New Title" in written
        assert "updated_at" in written

    @pytest.mark.asyncio
    async def test_update_note_no_content_no_frontmatter(self, tmp_path):
        """Neither content nor frontmatter → keeps both unchanged (lines 619, 627)."""
        vault_dir = tmp_path / "vault"
        vault_dir.mkdir()
        (vault_dir / "note.md").write_text("---\ntitle: Keep\n---\n# Keep body")

        adapter = _make_adapter()
        with patch.object(adapter, "_get_vault_path", return_value=str(vault_dir)):
            await adapter.update_note("myvault", "note.md")

        written = (vault_dir / "note.md").read_text()
        assert "Keep" in written


# ---------------------------------------------------------------------------
# delete_note — lines 659-689
# ---------------------------------------------------------------------------

class TestDeleteNote:
    @pytest.mark.asyncio
    async def test_delete_note_no_vault_path_raises(self):
        """No vault path → ObsidianCliError (line 663)."""
        adapter = _make_adapter()
        with patch.object(adapter, "_get_vault_path", return_value=None):
            with pytest.raises(_adapter_mod.ObsidianCliError, match="Cannot determine path"):
                await adapter.delete_note("myvault", "note.md")

    @pytest.mark.asyncio
    async def test_delete_note_file_not_exists_returns_false(self, tmp_path):
        """File does not exist → return False (line 668)."""
        vault_dir = tmp_path / "vault"
        vault_dir.mkdir()

        adapter = _make_adapter()
        with patch.object(adapter, "_get_vault_path", return_value=str(vault_dir)):
            result = await adapter.delete_note("myvault", "missing.md")
        assert result is False

    @pytest.mark.asyncio
    async def test_delete_note_with_backup(self, tmp_path):
        """backup=True → moves to .trash (lines 671-682)."""
        vault_dir = tmp_path / "vault"
        vault_dir.mkdir()
        (vault_dir / "note.md").write_text("# To Delete")

        adapter = _make_adapter()
        with patch.object(adapter, "_get_vault_path", return_value=str(vault_dir)):
            result = await adapter.delete_note("myvault", "note.md", backup=True)

        assert result is True
        assert not (vault_dir / "note.md").exists()
        trash_files = list((vault_dir / ".trash").rglob("*.md"))
        assert len(trash_files) == 1

    @pytest.mark.asyncio
    async def test_delete_note_permanent(self, tmp_path):
        """backup=False → permanent deletion (line 685)."""
        vault_dir = tmp_path / "vault"
        vault_dir.mkdir()
        (vault_dir / "note.md").write_text("# To Delete Permanently")

        adapter = _make_adapter()
        with patch.object(adapter, "_get_vault_path", return_value=str(vault_dir)):
            result = await adapter.delete_note("myvault", "note.md", backup=False)

        assert result is True
        assert not (vault_dir / "note.md").exists()

    @pytest.mark.asyncio
    async def test_delete_note_exception_raises_obsidian_error(self, tmp_path):
        """Exception during delete → ObsidianCliError (lines 688-689)."""
        import shutil
        vault_dir = tmp_path / "vault"
        vault_dir.mkdir()
        (vault_dir / "note.md").write_text("# Note")

        adapter = _make_adapter()
        with patch.object(adapter, "_get_vault_path", return_value=str(vault_dir)):
            with patch.object(shutil, "move", side_effect=OSError("disk full")):
                with pytest.raises(_adapter_mod.ObsidianCliError, match="Failed to delete"):
                    await adapter.delete_note("myvault", "note.md", backup=True)


# ---------------------------------------------------------------------------
# _write_note_to_filesystem — lines 701-740
# ---------------------------------------------------------------------------

class TestWriteNoteToFilesystem:
    @pytest.mark.asyncio
    async def test_no_vault_path_raises(self):
        """No vault path → ObsidianCliError (lines 703-707)."""
        adapter = _make_adapter()
        with patch.object(adapter, "_get_vault_path", return_value=None):
            with pytest.raises(_adapter_mod.ObsidianCliError, match="Cannot determine filesystem path"):
                await adapter._write_note_to_filesystem("myvault", "note.md", "content")

    @pytest.mark.asyncio
    async def test_vault_path_does_not_exist_raises(self, tmp_path):
        """Vault dir missing → ObsidianCliError (line 712)."""
        missing = tmp_path / "nonexistent"
        adapter = _make_adapter()
        with patch.object(adapter, "_get_vault_path", return_value=str(missing)):
            with pytest.raises(_adapter_mod.ObsidianCliError, match="does not exist"):
                await adapter._write_note_to_filesystem("myvault", "note.md", "content")

    @pytest.mark.asyncio
    async def test_vault_path_is_file_raises(self, tmp_path):
        """Vault path is file not dir → ObsidianCliError (line 714)."""
        vault_as_file = tmp_path / "file.txt"
        vault_as_file.write_text("not a dir")

        adapter = _make_adapter()
        with patch.object(adapter, "_get_vault_path", return_value=str(vault_as_file)):
            with pytest.raises(_adapter_mod.ObsidianCliError, match="not a directory"):
                await adapter._write_note_to_filesystem("myvault", "note.md", "content")

    @pytest.mark.asyncio
    async def test_path_traversal_raises(self, tmp_path):
        """Path resolves outside vault → ObsidianCliError (line 723)."""
        vault_dir = tmp_path / "vault"
        vault_dir.mkdir()

        adapter = _make_adapter()
        with patch.object(adapter, "_get_vault_path", return_value=str(vault_dir)):
            with pytest.raises(_adapter_mod.ObsidianCliError):
                await adapter._write_note_to_filesystem("myvault", "../outside.md", "evil")

    @pytest.mark.asyncio
    async def test_write_via_sync_executor(self, tmp_path):
        """Normal write via sync executor (no aiofiles) (lines 735-743)."""
        vault_dir = tmp_path / "vault"
        vault_dir.mkdir()

        adapter = _make_adapter()
        with patch.object(adapter, "_get_vault_path", return_value=str(vault_dir)):
            await adapter._write_note_to_filesystem("myvault", "note.md", "# Content")

        assert (vault_dir / "note.md").read_text() == "# Content"

    @pytest.mark.asyncio
    async def test_write_creates_parent_dirs(self, tmp_path):
        """Parent directories are created automatically (line 726)."""
        vault_dir = tmp_path / "vault"
        vault_dir.mkdir()

        adapter = _make_adapter()
        with patch.object(adapter, "_get_vault_path", return_value=str(vault_dir)):
            await adapter._write_note_to_filesystem("myvault", "subdir/deep/note.md", "# Deep")

        assert (vault_dir / "subdir" / "deep" / "note.md").read_text() == "# Deep"


# ---------------------------------------------------------------------------
# _sync_write_file — line 748
# ---------------------------------------------------------------------------

def test_sync_write_file(tmp_path):
    """_sync_write_file writes content to path (line 748)."""
    target = tmp_path / "out.md"
    _adapter_mod._sync_write_file(target, "hello world")
    assert target.read_text() == "hello world"


# ---------------------------------------------------------------------------
# _build_note_content — lines 756-806
# ---------------------------------------------------------------------------

class TestBuildNoteContent:
    def test_no_frontmatter_returns_content_as_is(self):
        """None frontmatter → just return content (line 756-757)."""
        result = _adapter_mod._build_note_content("plain content")
        assert result == "plain content"

    def test_empty_frontmatter_returns_content_as_is(self):
        """Empty dict frontmatter → just return content."""
        result = _adapter_mod._build_note_content("plain", {})
        assert result == "plain"

    def test_none_value_skipped(self):
        """None values in frontmatter → skipped (line 761-762)."""
        result = _adapter_mod._build_note_content("body", {"key": None, "other": "val"})
        assert "key" not in result
        assert "other: val" in result

    def test_list_value_expanded(self):
        """List value → YAML block sequence (lines 763-766)."""
        result = _adapter_mod._build_note_content("body", {"tags": ["a", "b"]})
        assert "tags:" in result
        assert "  - a" in result
        assert "  - b" in result

    def test_bool_true_lowercased(self):
        """Bool True → 'true' (lines 767-768)."""
        result = _adapter_mod._build_note_content("body", {"active": True})
        assert "active: true" in result

    def test_bool_false_lowercased(self):
        """Bool False → 'false' (lines 767-768)."""
        result = _adapter_mod._build_note_content("body", {"archived": False})
        assert "archived: false" in result

    def test_int_value(self):
        """Int value → numeric (lines 769-770)."""
        result = _adapter_mod._build_note_content("body", {"count": 42})
        assert "count: 42" in result

    def test_float_value(self):
        """Float value → numeric (lines 769-770)."""
        result = _adapter_mod._build_note_content("body", {"score": 3.14})
        assert "score: 3.14" in result

    def test_string_with_colon_quoted(self):
        """String with ':' → double-quoted (lines 773-800)."""
        result = _adapter_mod._build_note_content("body", {"title": "Hello: World"})
        assert '"Hello: World"' in result

    def test_string_with_hash_quoted(self):
        """String with '#' → double-quoted."""
        result = _adapter_mod._build_note_content("body", {"title": "Tag #1"})
        assert '"' in result

    def test_plain_string_no_quoting(self):
        """Plain string → no quoting (line 801)."""
        result = _adapter_mod._build_note_content("body", {"title": "SimpleTitle"})
        assert "title: SimpleTitle" in result

    def test_full_frontmatter_block_structure(self):
        """Full block structure: --- delimiters, blank line, content."""
        result = _adapter_mod._build_note_content("Body text", {"title": "Test", "count": 1})
        lines = result.splitlines()
        assert lines[0] == "---"
        assert "---" in lines[1:]
        assert lines[-1] == "Body text"
