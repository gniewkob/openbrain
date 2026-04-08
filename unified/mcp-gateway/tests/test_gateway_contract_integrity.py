import json
import unittest
from pathlib import Path

from helpers import load_gateway_main


class GatewayContractIntegrityTests(unittest.TestCase):
    def _contracts_dir(self) -> Path:
        return Path(__file__).resolve().parents[2] / "contracts"

    def test_all_contract_files_are_valid_json(self) -> None:
        for path in self._contracts_dir().glob("*.json"):
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertIsInstance(data, dict, f"{path.name} must contain JSON object")

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
