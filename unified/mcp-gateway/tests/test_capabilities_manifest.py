import unittest

from helpers import load_gateway_main


class GatewayCapabilitiesManifestTests(unittest.TestCase):
    def test_main_constants_match_loaded_manifest(self) -> None:
        gateway = load_gateway_main()
        manifest = gateway.load_capabilities_manifest()

        self.assertEqual(gateway.CORE_TOOLS, manifest["core_tools"])
        self.assertEqual(gateway.ADVANCED_TOOLS, manifest["advanced_tools"])
        self.assertEqual(gateway.ADMIN_TOOLS, manifest["admin_tools"])
        self.assertEqual(gateway.OBSIDIAN_LOCAL_TOOLS, manifest["local_obsidian_tools"])

