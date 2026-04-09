import unittest

from helpers import load_gateway_main


class GatewayRuntimeAndNormalizersTests(unittest.TestCase):
    def test_runtime_limits_loaded_into_constants(self) -> None:
        gateway = load_gateway_main()
        limits = gateway.load_runtime_limits()
        self.assertEqual(gateway.MAX_SEARCH_TOP_K, limits["max_search_top_k"])
        self.assertEqual(gateway.MAX_LIST_LIMIT, limits["max_list_limit"])
        self.assertEqual(gateway.MAX_SYNC_LIMIT, limits["max_sync_limit"])

    def test_normalize_find_hits_to_records(self) -> None:
        gateway = load_gateway_main()
        records = gateway.normalize_find_hits_to_records(
            [
                {
                    "record": {
                        "id": "mem-1",
                        "domain": "build",
                        "created_by": "  creator  ",
                        "updated_by": "   ",
                    },
                    "score": 1.0,
                }
            ]
        )
        self.assertEqual(records[0]["id"], "mem-1")
        self.assertEqual(records[0]["domain"], "build")
        self.assertEqual(records[0]["created_by"], "creator")
        self.assertEqual(records[0]["updated_by"], "creator")

    def test_normalize_find_hits_to_scored_memories(self) -> None:
        gateway = load_gateway_main()
        scored = gateway.normalize_find_hits_to_scored_memories(
            [
                {
                    "record": {
                        "id": "mem-1",
                        "domain": "build",
                        "created_by": "  creator  ",
                        "updated_by": "   ",
                    },
                    "score": 1.0,
                }
            ]
        )
        self.assertEqual(scored[0]["score"], 1.0)
        self.assertEqual(scored[0]["memory"]["id"], "mem-1")
        self.assertEqual(scored[0]["memory"]["domain"], "build")
        self.assertEqual(scored[0]["memory"]["created_by"], "creator")
        self.assertEqual(scored[0]["memory"]["updated_by"], "creator")
