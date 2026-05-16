import unittest
from unittest.mock import MagicMock, AsyncMock, patch
from common.obsidian_adapter import (
    ObsidianCliAdapter,
    ObsidianCliError,
    ObsidianNote,
)

class TestObsidianAdapter(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        # Mock configuration to avoid loading from environment
        self.mock_config = MagicMock()
        self.mock_config.obsidian.cli_command = "obsidian"

        # Patch the config loader to return our mock
        # Note: We use the function path inside common.obsidian_adapter
        with patch("common.obsidian_adapter._load_config_getter",
                   return_value=lambda: self.mock_config):
            self.adapter = ObsidianCliAdapter()

    @patch.object(ObsidianCliAdapter, "_run", new_callable=AsyncMock)
    async def test_list_files_cli_fallback(self, mock_run):
        """Test listing files via CLI fallback when filesystem access is unavailable."""
        mock_run.return_value = "note1.md\nnote2.md\n"

        # Force CLI fallback by making _get_vault_path return None
        with patch.object(self.adapter, "_get_vault_path", return_value=None):
            files = await self.adapter.list_files("test-vault")

        self.assertEqual(files, ["note1.md", "note2.md"])
        mock_run.assert_any_call("files", "ext=md", "vault=test-vault")

    @patch.object(ObsidianCliAdapter, "_run", new_callable=AsyncMock)
    async def test_read_note_cli_fallback(self, mock_run):
        """Test reading a note via CLI fallback."""
        mock_run.side_effect = [
            "---\ntitle: Test Note\n---\nContent", # note content
            '["tag1", "tag2"]' # note tags
        ]

        with patch.object(self.adapter, "_get_vault_path", return_value=None):
            note = await self.adapter.read_note("test-vault", "test-note.md")

        self.assertEqual(note.title, "Test Note")
        self.assertEqual(note.content, "---\ntitle: Test Note\n---\nContent")
        self.assertEqual(note.tags, ["tag1", "tag2"])

    @patch.object(ObsidianCliAdapter, "read_note", new_callable=AsyncMock)
    @patch.object(ObsidianCliAdapter, "_write_note_to_filesystem", new_callable=AsyncMock)
    async def test_write_note_new(self, mock_write_fs, mock_read_note):
        """Test writing a new note (where it doesn't already exist)."""
        # First call to read_note (existence check) fails, second call (verification) succeeds
        mock_read_note.side_effect = [
            ObsidianCliError("not found"),
            ObsidianNote(
                vault="v", path="p.md", title="t", content="c",
                frontmatter={}, tags=[], file_hash="hash"
            )
        ]

        note = await self.adapter.write_note("v", "p.md", "content", overwrite=False)

        self.assertEqual(note.path, "p.md")
        # _build_note_content returns just content if frontmatter is None
        mock_write_fs.assert_called_once_with("v", "p.md", "content")

    async def test_note_exists(self):
        """Test the note_exists utility method."""
        # Case 1: Note exists
        with patch.object(self.adapter, "read_note", return_value=MagicMock()):
            self.assertTrue(await self.adapter.note_exists("v", "p.md"))

        # Case 2: Note does not exist
        with patch.object(self.adapter, "read_note", side_effect=ObsidianCliError("not found")):
            self.assertFalse(await self.adapter.note_exists("v", "p.md"))

    def test_validate_vault_path(self):
        """Test path validation logic for security (preventing traversal)."""
        # Invalid vault (traversal)
        with self.assertRaisesRegex(ObsidianCliError, "Invalid vault name"):
            self.adapter._validate_vault_path("../evil-vault")

        # Invalid note path (absolute)
        with self.assertRaisesRegex(ObsidianCliError, "Invalid note path"):
            self.adapter._validate_vault_path("vault", "/absolute/path")

    async def test_get_vault_path_env(self):
        """Test discovery of vault paths from individual environment variables."""
        with patch.dict("os.environ", {"OBSIDIAN_VAULT_MY_VAULT_PATH": "/path/to/vault"}):
            # Clear internal cache to ensure fresh lookup
            from common.obsidian_adapter import _VAULT_PATHS_CACHE
            _VAULT_PATHS_CACHE.clear()

            path = await self.adapter._get_vault_path("My Vault")
            self.assertEqual(path, "/path/to/vault")

if __name__ == "__main__":
    unittest.main()
