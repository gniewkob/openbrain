import json
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from helpers import load_gateway_main


class GatewayCapabilitiesResponseContractTests(unittest.IsolatedAsyncioTestCase):
    def _contract(self) -> dict:
        path = (
            Path(__file__).resolve().parents[2]
            / "contracts"
            / "capabilities_response_contract.json"
        )
        return json.loads(path.read_text(encoding="utf-8"))

    def _metadata(self) -> dict:
        path = (
            Path(__file__).resolve().parents[2]
            / "contracts"
            / "capabilities_metadata.json"
        )
        return json.loads(path.read_text(encoding="utf-8"))

    def _manifest(self) -> dict:
        path = (
            Path(__file__).resolve().parents[2]
            / "contracts"
            / "capabilities_manifest.json"
        )
        return json.loads(path.read_text(encoding="utf-8"))

    async def test_gateway_capabilities_follow_response_contract(self) -> None:
        gateway = load_gateway_main()
        contract = self._contract()
        metadata = self._metadata()
        manifest = self._manifest()
        backend = {
            "status": "ok",
            "api": "reachable",
            "db": "ok",
            "vector_store": "ok",
            "probe": "readyz",
        }

        with (
            patch("_gateway_src.main._get_backend_status", new=AsyncMock(return_value=backend)),
            patch("_gateway_src.main._obsidian_local_tools_enabled", return_value=False),
        ):
            caps = await gateway.brain_capabilities()

        for key in contract["required_top_level_keys"]:
            self.assertIn(key, caps)
        self.assertEqual(caps["api_version"], metadata["api_version"])
        self.assertEqual(caps["schema_changelog"], metadata["schema_changelog"])
        for key in contract["backend_required_keys"]:
            self.assertIn(key, caps["backend"])
        for key in contract["health_required_keys"]:
            self.assertIn(key, caps["health"])
        for key in contract["health_component_required_keys"]:
            self.assertIn(key, caps["health"]["components"])
        for key in contract["obsidian_required_keys"]:
            self.assertIn(key, caps["obsidian"])

        self.assertIn(caps["health"]["overall"], contract["health_overall_values"])
        self.assertIn(caps["obsidian"]["mode"], contract["obsidian_modes"])
        self.assertIn(caps["obsidian"]["status"], contract["obsidian_statuses"])
        self.assertIsInstance(caps["obsidian"]["tools"], list)
        self.assertEqual(caps["tier_1_core"]["tools"], manifest["core_tools"])
        self.assertEqual(caps["tier_2_advanced"]["tools"], manifest["advanced_tools"])
        self.assertEqual(caps["tier_3_admin"]["tools"], manifest["admin_tools"])
        self.assertIn("test_data_report", caps["tier_3_admin"]["tools"])
        self.assertIn("cleanup_build_test_data", caps["tier_3_admin"]["tools"])
