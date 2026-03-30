import unittest
from unittest.mock import AsyncMock, Mock, patch

from helpers import load_gateway_main


class GatewayObsidianToolTests(unittest.IsolatedAsyncioTestCase):
    async def test_brain_obsidian_vaults_requires_explicit_opt_in(self) -> None:
        gateway = load_gateway_main()

        with patch.dict("os.environ", {}, clear=False):
            with self.assertRaises(ValueError) as ctx:
                await gateway.brain_obsidian_vaults()

        self.assertIn("ENABLE_LOCAL_OBSIDIAN_TOOLS=1", str(ctx.exception))

    async def test_brain_obsidian_vaults_uses_local_adapter(self) -> None:
        gateway = load_gateway_main()

        with patch.dict("os.environ", {"ENABLE_LOCAL_OBSIDIAN_TOOLS": "1"}, clear=False), patch("_gateway_src.main.ObsidianCliAdapter") as adapter_cls:
            adapter = AsyncMock()
            adapter.list_vaults.return_value = ["Documents"]
            adapter_cls.return_value = adapter

            result = await gateway.brain_obsidian_vaults()

        adapter.list_vaults.assert_awaited_once_with()
        self.assertEqual(result, ["Documents"])

    async def test_brain_obsidian_read_note_uses_local_adapter(self) -> None:
        gateway = load_gateway_main()

        with patch.dict("os.environ", {"ENABLE_LOCAL_OBSIDIAN_TOOLS": "1"}, clear=False), patch("_gateway_src.main.ObsidianCliAdapter") as adapter_cls:
            adapter = AsyncMock()
            adapter.read_note.return_value = Mock(
                vault="Documents",
                path="Inbox/Test.md",
                title="Test",
                content="Body",
                frontmatter={"domain": "build"},
                tags=["openbrain"],
                file_hash="abc",
            )
            adapter_cls.return_value = adapter

            result = await gateway.brain_obsidian_read_note(path="Inbox/Test.md", vault="Documents")

        adapter.read_note.assert_awaited_once_with("Documents", "Inbox/Test.md")
        self.assertEqual(result["path"], "Inbox/Test.md")

    async def test_brain_obsidian_sync_reads_local_notes_and_writes_v1(self) -> None:
        gateway = load_gateway_main()
        response = Mock()
        response.is_error = False
        response.json.return_value = {"summary": {"received": 1}, "results": [{"status": "created"}]}

        with patch.dict("os.environ", {"ENABLE_LOCAL_OBSIDIAN_TOOLS": "1"}, clear=False), patch("_gateway_src.main.ObsidianCliAdapter") as adapter_cls, patch("_gateway_src.main._client") as mock_client:
            adapter = AsyncMock()
            adapter.list_files.return_value = ["Inbox/Test.md"]
            adapter.read_note.return_value = Mock(
                vault="Documents",
                path="Inbox/Test.md",
                title="Test",
                content="Body",
                frontmatter={},
                tags=["openbrain"],
                file_hash="abc",
            )
            adapter_cls.return_value = adapter

            client = AsyncMock()
            client.__aenter__.return_value = client
            client.__aexit__.return_value = False
            client.post.return_value = response
            mock_client.return_value = client

            result = await gateway.brain_obsidian_sync(vault="Documents", folder="Inbox", limit=1)

        adapter.list_files.assert_awaited_once_with("Documents", folder="Inbox", limit=1)
        adapter.read_note.assert_awaited_once_with("Documents", "Inbox/Test.md")
        client.post.assert_awaited_once()
        self.assertEqual(result["scanned"], 1)

    async def test_brain_capabilities_hides_obsidian_tools_when_disabled(self) -> None:
        gateway = load_gateway_main()

        with patch.dict("os.environ", {}, clear=False):
            result = await gateway.brain_capabilities()

        self.assertNotIn("obsidian_vaults", result["tier_2_advanced"]["tools"])

    async def test_brain_capabilities_includes_obsidian_tools_when_enabled(self) -> None:
        gateway = load_gateway_main()

        with patch.dict("os.environ", {"ENABLE_LOCAL_OBSIDIAN_TOOLS": "1"}, clear=False):
            result = await gateway.brain_capabilities()

        self.assertIn("obsidian_vaults", result["tier_2_advanced"]["tools"])


if __name__ == "__main__":
    unittest.main()
