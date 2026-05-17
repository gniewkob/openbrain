from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch
import unittest

# Add src to sys.path to allow both 'from capabilities_manifest' and 'from src.capabilities_manifest'
# depending on how the test runner is configured.
repo_root = Path(__file__).resolve().parents[2]
src_path = str(repo_root / "unified" / "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)

try:
    from capabilities_manifest import _validate_manifest, load_capabilities_manifest
except ImportError:
    from src.capabilities_manifest import _validate_manifest, load_capabilities_manifest


class TestCapabilitiesManifest(unittest.TestCase):
    def test_validate_manifest_valid_data(self):
        data = {
            "core_tools": ["search", "get"],
            "advanced_tools": ["list"],
            "admin_tools": ["maintain"],
            "http_obsidian_tools": ["obsidian_vaults"],
            "local_obsidian_tools": ["obsidian_vaults", "obsidian_sync"],
        }
        normalized = _validate_manifest(data)
        self.assertEqual(normalized, data)

    def test_validate_manifest_not_a_dict(self):
        with self.assertRaisesRegex(ValueError, "capabilities_manifest must be a JSON object"):
            _validate_manifest(["not", "a", "dict"])

    def test_validate_manifest_missing_key(self):
        data = {
            "core_tools": ["search"],
            # Missing advanced_tools
            "admin_tools": ["maintain"],
            "http_obsidian_tools": ["obsidian_vaults"],
            "local_obsidian_tools": ["obsidian_vaults"],
        }
        with self.assertRaisesRegex(ValueError, "capabilities_manifest.advanced_tools must be a non-empty string list"):
            _validate_manifest(data)

    def test_validate_manifest_not_a_list(self):
        data = {
            "core_tools": "not a list",
            "advanced_tools": ["list"],
            "admin_tools": ["maintain"],
            "http_obsidian_tools": ["obsidian_vaults"],
            "local_obsidian_tools": ["obsidian_vaults"],
        }
        with self.assertRaisesRegex(ValueError, "capabilities_manifest.core_tools must be a non-empty string list"):
            _validate_manifest(data)

    def test_validate_manifest_list_with_non_strings(self):
        data = {
            "core_tools": ["search", 123],
            "advanced_tools": ["list"],
            "admin_tools": ["maintain"],
            "http_obsidian_tools": ["obsidian_vaults"],
            "local_obsidian_tools": ["obsidian_vaults"],
        }
        with self.assertRaisesRegex(ValueError, "capabilities_manifest.core_tools must be a non-empty string list"):
            _validate_manifest(data)

    def test_validate_manifest_list_with_empty_strings(self):
        data = {
            "core_tools": ["search", ""],
            "advanced_tools": ["list"],
            "admin_tools": ["maintain"],
            "http_obsidian_tools": ["obsidian_vaults"],
            "local_obsidian_tools": ["obsidian_vaults"],
        }
        with self.assertRaisesRegex(ValueError, "capabilities_manifest.core_tools must be a non-empty string list"):
            _validate_manifest(data)

        data["core_tools"] = ["search", "  "]
        with self.assertRaisesRegex(ValueError, "capabilities_manifest.core_tools must be a non-empty string list"):
            _validate_manifest(data)

    def test_validate_manifest_list_with_duplicates(self):
        data = {
            "core_tools": ["search", "search"],
            "advanced_tools": ["list"],
            "admin_tools": ["maintain"],
            "http_obsidian_tools": ["obsidian_vaults"],
            "local_obsidian_tools": ["obsidian_vaults"],
        }
        with self.assertRaisesRegex(ValueError, "capabilities_manifest.core_tools must not contain duplicates"):
            _validate_manifest(data)

    def test_load_capabilities_manifest(self):
        mock_data = {
            "core_tools": ["search"],
            "advanced_tools": ["list"],
            "admin_tools": ["maintain"],
            "http_obsidian_tools": ["obsidian_vaults"],
            "local_obsidian_tools": ["obsidian_vaults"],
        }
        with patch.object(Path, "read_text", return_value=json.dumps(mock_data)):
            result = load_capabilities_manifest()
            self.assertEqual(result, mock_data)
