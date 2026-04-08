import unittest

from helpers import load_gateway_main


class GatewayRequestBuildersTests(unittest.TestCase):
    def test_build_find_list_payload_defaults(self) -> None:
        gateway = load_gateway_main()
        payload = gateway.build_find_list_payload(limit=3, filters={"domain": "build"})
        self.assertEqual(
            payload,
            {
                "query": None,
                "filters": {"domain": "build"},
                "limit": 3,
                "sort": "updated_at_desc",
            },
        )

    def test_normalize_updated_by(self) -> None:
        gateway = load_gateway_main()
        self.assertEqual(gateway.normalize_updated_by("  bob  "), "bob")
        self.assertEqual(gateway.normalize_updated_by("   "), "agent")
        self.assertEqual(gateway.normalize_updated_by(None), "agent")

    def test_build_find_search_payload(self) -> None:
        gateway = load_gateway_main()
        payload = gateway.build_find_search_payload(
            query="ops",
            limit=4,
            filters={"domain": "corporate"},
        )
        self.assertEqual(
            payload,
            {"query": "ops", "limit": 4, "filters": {"domain": "corporate"}},
        )

    def test_build_sync_check_payload(self) -> None:
        gateway = load_gateway_main()
        payload = gateway.build_sync_check_payload(
            match_key="mk:abc",
            file_hash="sha256:xyz",
        )
        self.assertEqual(
            payload,
            {
                "memory_id": None,
                "match_key": "mk:abc",
                "obsidian_ref": None,
                "file_hash": "sha256:xyz",
            },
        )

    def test_validate_store_inputs_corporate_requires_owner_and_match_key(self) -> None:
        gateway = load_gateway_main()
        with self.assertRaises(ValueError):
            gateway.validate_store_inputs(
                domain="corporate",
                owner="",
                match_key="mk:1",
            )
        with self.assertRaises(ValueError):
            gateway.validate_store_inputs(
                domain="corporate",
                owner="ops@example.com",
                match_key=None,
            )

    def test_validate_store_inputs_non_corporate_allows_empty_fields(self) -> None:
        gateway = load_gateway_main()
        gateway.validate_store_inputs(
            domain="build",
            owner="",
            match_key=None,
        )
