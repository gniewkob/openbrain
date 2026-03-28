import sys
import types
import unittest

from src.obsidian_cli import _clean_cli_output, _parse_frontmatter, note_to_memory_write_record, ObsidianNote


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


if __name__ == "__main__":
    unittest.main()
