import unittest

from helpers import load_gateway_main


class GatewayMemoryPathsTests(unittest.TestCase):
    def test_memory_paths_contract_values(self) -> None:
        gateway = load_gateway_main()
        self.assertEqual(gateway.memory_absolute_path("find"), "/api/v1/memory/find")
        self.assertEqual(gateway.memory_absolute_path("write_many"), "/api/v1/memory/write-many")

    def test_memory_item_absolute_path(self) -> None:
        gateway = load_gateway_main()
        self.assertEqual(gateway.memory_item_absolute_path("mem-1"), "/api/v1/memory/mem-1")

