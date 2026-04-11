import asyncio
import json
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from helpers import load_gateway_main


class GatewayContractIntegrityTests(unittest.TestCase):
    def _contracts_dir(self) -> Path:
        return Path(__file__).resolve().parents[2] / "contracts"

    def test_all_contract_files_are_valid_json(self) -> None:
        for path in self._contracts_dir().glob("*.json"):
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertIsInstance(data, dict, f"{path.name} must contain JSON object")

    def test_capabilities_tier_status_change_is_versioned_in_metadata(self) -> None:
        meta = json.loads(
            (self._contracts_dir() / "capabilities_metadata.json").read_text(
                encoding="utf-8"
            )
        )
        response_contract = json.loads(
            (self._contracts_dir() / "capabilities_response_contract.json").read_text(
                encoding="utf-8"
            )
        )

        tier_status_values = response_contract.get("tier_status_values", [])
        self.assertTrue(
            tier_status_values,
            "capabilities response contract must define tier_status_values",
        )

        api_version = meta.get("api_version")
        self.assertIsInstance(api_version, str)
        self.assertRegex(api_version, r"^\d+\.\d+\.\d+$")

        changelog = meta.get("schema_changelog", {})
        self.assertIn(
            api_version,
            changelog,
            "schema_changelog must include current capabilities metadata api_version",
        )
        self.assertIn(
            "tier status",
            str(changelog[api_version]).lower(),
            "latest capabilities metadata changelog entry must document tier status semantics",
        )

    def test_gateway_constants_follow_contracts(self) -> None:
        gateway = load_gateway_main()
        caps = json.loads(
            (self._contracts_dir() / "capabilities_manifest.json").read_text(
                encoding="utf-8"
            )
        )
        meta = json.loads(
            (self._contracts_dir() / "capabilities_metadata.json").read_text(
                encoding="utf-8"
            )
        )
        limits = json.loads(
            (self._contracts_dir() / "runtime_limits.json").read_text(encoding="utf-8")
        )

        self.assertEqual(gateway.CORE_TOOLS, caps["core_tools"])
        self.assertEqual(gateway.ADVANCED_TOOLS, caps["advanced_tools"])
        self.assertEqual(gateway.ADMIN_TOOLS, caps["admin_tools"])
        self.assertEqual(gateway._CAP_META["api_version"], meta["api_version"])
        self.assertEqual(
            gateway._CAP_META["schema_changelog"], meta["schema_changelog"]
        )
        self.assertEqual(gateway.MAX_SEARCH_TOP_K, limits["max_search_top_k"])
        self.assertEqual(gateway.MAX_LIST_LIMIT, limits["max_list_limit"])
        self.assertEqual(gateway.MAX_SYNC_LIMIT, limits["max_sync_limit"])

    def test_gateway_path_helpers_follow_contract(self) -> None:
        gateway = load_gateway_main()
        paths = json.loads(
            (self._contracts_dir() / "memory_paths.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            gateway.memory_absolute_path("find"),
            f'{paths["memory_base"]}{paths["paths"]["find"]}',
        )
        self.assertEqual(
            gateway.memory_absolute_path("sync_check"),
            f'{paths["memory_base"]}{paths["paths"]["sync_check"]}',
        )

    def test_capabilities_tools_map_to_real_gateway_functions(self) -> None:
        gateway = load_gateway_main()
        caps = json.loads(
            (self._contracts_dir() / "capabilities_manifest.json").read_text(
                encoding="utf-8"
            )
        )

        expected = {"capabilities"}
        expected.update(caps["core_tools"])
        expected.update(caps["advanced_tools"])
        expected.update(caps["admin_tools"])
        expected.update(caps["local_obsidian_tools"])

        for tool in sorted(expected):
            fn = getattr(gateway, f"brain_{tool}", None)
            self.assertTrue(
                callable(fn),
                f"brain_{tool} must be implemented by gateway runtime",
            )

    def test_gateway_obsidian_capabilities_follow_runtime_registration_state(self) -> None:
        gateway = load_gateway_main()
        caps_manifest = json.loads(
            (self._contracts_dir() / "capabilities_manifest.json").read_text(
                encoding="utf-8"
            )
        )
        backend = {
            "status": "ok",
            "api": "reachable",
            "db": "ok",
            "vector_store": "ok",
            "probe": "readyz",
        }

        with (
            patch("_gateway_src.main._get_backend_status", AsyncMock(return_value=backend)),
            patch("_gateway_src.main._obsidian_local_tools_enabled", return_value=True),
            patch("_gateway_src.main._local_obsidian_tools_registered", return_value=True),
        ):
            enabled_caps = asyncio.run(gateway.brain_capabilities())

        self.assertEqual(enabled_caps["obsidian_local"]["status"], "enabled")
        self.assertEqual(
            enabled_caps["obsidian_local"]["tools"], caps_manifest["local_obsidian_tools"]
        )

        with (
            patch("_gateway_src.main._get_backend_status", AsyncMock(return_value=backend)),
            patch("_gateway_src.main._obsidian_local_tools_enabled", return_value=True),
            patch("_gateway_src.main._local_obsidian_tools_registered", return_value=False),
        ):
            disabled_caps = asyncio.run(gateway.brain_capabilities())

        self.assertEqual(disabled_caps["obsidian_local"]["status"], "disabled")
        self.assertEqual(disabled_caps["obsidian_local"]["tools"], [])
