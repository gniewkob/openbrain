import os
import sys
import types
import unittest
from unittest.mock import AsyncMock, patch

from src.common.obsidian_adapter import (
    _clean_cli_output,
    _configured_vault_names_from_env,
    _parse_vault_paths_mapping,
    _parse_frontmatter,
    note_to_memory_write_record,
    ObsidianCliAdapter,
    ObsidianCliError,
    ObsidianNote,
)


class ObsidianCliHelperTests(unittest.TestCase):
    def test_clean_cli_output_strips_installer_noise(self) -> None:
        raw = (
            "2026-03-27 18:50:12 Loading updated app package /tmp/obsidian.asar\n"
            "Your Obsidian installer is out of date. Please download the latest installer.\n"
            "Documents\n"
        )

        self.assertEqual(_clean_cli_output(raw), "Documents")

    def test_parse_frontmatter_supports_lists_and_body(self) -> None:
        content = (
            "---\n"
            "title: Architecture Audit\n"
            "domain: build\n"
            "tags:\n"
            "  - openbrain\n"
            "  - obsidian\n"
            "---\n"
            "# Architecture Audit\n"
            "Body\n"
        )

        frontmatter, body = _parse_frontmatter(content)

        self.assertEqual(frontmatter["title"], "Architecture Audit")
        self.assertEqual(frontmatter["domain"], "build")
        self.assertEqual(frontmatter["tags"], ["openbrain", "obsidian"])
        self.assertEqual(body, "# Architecture Audit\nBody")

    def test_note_to_memory_write_record_uses_frontmatter_defaults_and_match_key(self) -> None:
        fake_schemas = types.ModuleType("src.schemas")

        class FakeSourceMetadata:
            def __init__(self, **kwargs) -> None:
                self.__dict__.update(kwargs)

        class FakeMemoryWriteRecord:
            def __init__(self, **kwargs) -> None:
                self.__dict__.update(kwargs)

        fake_schemas.SourceMetadata = FakeSourceMetadata
        fake_schemas.MemoryWriteRecord = FakeMemoryWriteRecord
        sys.modules["src.schemas"] = fake_schemas
        try:
            note = ObsidianNote(
                vault="Documents",
                path="Architecture/OpenBrain.md",
                content="---\ndomain: build\nentity_type: Architecture\ntags: [openbrain, obsidian]\n---\nBody",
                frontmatter={"domain": "build", "entity_type": "Architecture", "tags": ["openbrain", "obsidian"]},
                tags=["openbrain", "obsidian"],
                title="OpenBrain",
                file_hash="hash",
            )

            record = note_to_memory_write_record(
                note,
                default_domain="personal",
                default_entity_type="Note",
                default_owner="gniewkob",
                default_tags=["sync"],
            )

            self.assertEqual(record.match_key, "obsidian:Documents:Architecture/OpenBrain.md")
            self.assertEqual(record.domain, "build")
            self.assertEqual(record.entity_type, "Architecture")
            self.assertEqual(record.owner, "gniewkob")
            self.assertEqual(record.tags, ["sync", "openbrain", "obsidian"])
            self.assertEqual(record.obsidian_ref, "Architecture/OpenBrain.md")
        finally:
            del sys.modules["src.schemas"]


class ObsidianVaultDiscoveryTests(unittest.IsolatedAsyncioTestCase):
    def test_parse_vault_paths_mapping_supports_legacy_format(self) -> None:
        parsed = _parse_vault_paths_mapping(
            "Memory:/vault/memory, Work:/vault/work,InvalidEntry"
        )
        self.assertEqual(parsed, {"Memory": "/vault/memory", "Work": "/vault/work"})

    def test_parse_vault_paths_mapping_supports_braced_legacy_format(self) -> None:
        parsed = _parse_vault_paths_mapping(
            "{Memory:/vault/memory,Work:/vault/work}"
        )
        self.assertEqual(parsed, {"Memory": "/vault/memory", "Work": "/vault/work"})

    def test_configured_vaults_from_json_and_named_env(self) -> None:
        with patch.dict(
            os.environ,
            {
                "OBSIDIAN_VAULT_PATHS": '{"Documents":"/tmp/docs"}',
                "OBSIDIAN_VAULT_TEAM_NOTES_PATH": "/tmp/team",
            },
            clear=False,
        ):
            names = _configured_vault_names_from_env()
        self.assertEqual(names, ["Documents", "TEAM NOTES"])

    async def test_list_vaults_falls_back_to_env_when_cli_unavailable(self) -> None:
        adapter = ObsidianCliAdapter(command="obsidian")
        with patch.object(
            adapter,
            "_run",
            new=AsyncMock(side_effect=ObsidianCliError("cli unavailable")),
        ), patch.dict(
            os.environ,
            {"OBSIDIAN_VAULT_PATHS": '{"Controlled":"/tmp/controlled"}'},
            clear=False,
        ):
            vaults = await adapter.list_vaults()

        self.assertEqual(vaults, ["Controlled"])

    async def test_list_vaults_raises_when_cli_unavailable_and_no_env(self) -> None:
        adapter = ObsidianCliAdapter(command="obsidian")
        with patch.object(
            adapter,
            "_run",
            new=AsyncMock(side_effect=ObsidianCliError("cli unavailable")),
        ), patch.dict(
            os.environ, {}, clear=True
        ):
            with self.assertRaises(ObsidianCliError):
                await adapter.list_vaults()


if __name__ == "__main__":
    unittest.main()
