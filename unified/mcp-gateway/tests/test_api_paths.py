import unittest
from unittest.mock import AsyncMock, Mock, patch

from helpers import load_gateway_main


class GatewayApiPathTests(unittest.IsolatedAsyncioTestCase):
    async def test_brain_store_uses_configured_source_system(self) -> None:
        gateway = load_gateway_main()
        response = Mock()
        response.is_error = False
        response.json.return_value = {
            "record": {
                "id": "mem-1",
                "tenant_id": None,
                "domain": "build",
                "entity_type": "Decision",
                "content": "payload",
                "owner": "",
                "status": "active",
                "version": 1,
                "sensitivity": "internal",
                "superseded_by": None,
                "tags": [],
                "relations": {},
                "obsidian_ref": None,
                "custom_fields": {},
                "content_hash": "hash",
                "match_key": None,
                "previous_id": None,
                "root_id": "mem-1",
                "valid_from": None,
                "created_at": "2026-04-01T00:00:00Z",
                "updated_at": "2026-04-01T00:00:00Z",
                "created_by": "tester",
                "updated_by": None,
            }
        }

        with (
            patch("_gateway_src.main._client") as mock_client,
            patch.object(gateway, "MCP_SOURCE_SYSTEM", "codex"),
        ):
            client = AsyncMock()
            client.__aenter__.return_value = client
            client.__aexit__.return_value = False
            client.post.return_value = response
            mock_client.return_value = client

            await gateway.brain_store(content="payload", domain="build")

        client.post.assert_awaited_once_with(
            "/api/v1/memory/write",
            json={
                "record": {
                    "content": "payload",
                    "domain": "build",
                    "entity_type": "Decision",
                    "title": None,
                    "sensitivity": "internal",
                    "owner": "",
                    "tenant_id": None,
                    "tags": [],
                    "custom_fields": {},
                    "obsidian_ref": None,
                    "match_key": None,
                    "source": {"type": "agent", "system": "codex"},
                },
                "write_mode": "upsert",
            },
        )

    async def test_brain_store_corporate_with_owner_and_match_key_succeeds(
        self,
    ) -> None:
        gateway = load_gateway_main()
        response = Mock()
        response.is_error = False
        response.json.return_value = {
            "record": {
                "id": "mem-corp-1",
                "tenant_id": None,
                "domain": "corporate",
                "entity_type": "Decision",
                "content": "policy",
                "owner": "ops@example.com",
                "status": "active",
                "version": 2,
                "sensitivity": "internal",
                "superseded_by": None,
                "tags": [],
                "relations": {},
                "obsidian_ref": None,
                "custom_fields": {},
                "content_hash": "hash",
                "match_key": "corp:policy:auth:v2",
                "previous_id": "mem-corp-0",
                "root_id": "mem-corp-0",
                "valid_from": None,
                "created_at": "2026-04-01T00:00:00Z",
                "updated_at": "2026-04-01T00:00:00Z",
                "created_by": "tester",
                "updated_by": None,
            }
        }

        with patch("_gateway_src.main._client") as mock_client:
            client = AsyncMock()
            client.__aenter__.return_value = client
            client.__aexit__.return_value = False
            client.post.return_value = response
            mock_client.return_value = client

            memory = await gateway.brain_store(
                content="policy",
                domain="corporate",
                owner=" ops@example.com ",
                match_key=" corp:policy:auth:v2 ",
            )

        self.assertEqual(memory.domain, "corporate")
        self.assertEqual(memory.owner, "ops@example.com")
        self.assertEqual(memory.match_key, "corp:policy:auth:v2")
        client.post.assert_awaited_once_with(
            "/api/v1/memory/write",
            json={
                "record": {
                    "content": "policy",
                    "domain": "corporate",
                    "entity_type": "Decision",
                    "title": None,
                    "sensitivity": "internal",
                    "owner": "ops@example.com",
                    "tenant_id": None,
                    "tags": [],
                    "custom_fields": {},
                    "obsidian_ref": None,
                    "match_key": "corp:policy:auth:v2",
                    "source": {"type": "agent", "system": "other"},
                },
                "write_mode": "upsert",
            },
        )

    async def test_brain_store_corporate_missing_contract_fields_raises(self) -> None:
        gateway = load_gateway_main()
        with patch("_gateway_src.main._client") as mock_client:
            with self.assertRaises(ValueError):
                await gateway.brain_store(
                    content="policy",
                    domain="corporate",
                    owner="",
                    match_key="corp:policy:auth:v2",
                )
            mock_client.assert_not_called()

    async def test_brain_list_calls_api_memories_path(self) -> None:
        gateway = load_gateway_main()
        response = Mock()
        response.is_error = False
        response.json.return_value = []

        with patch("_gateway_src.main._client") as mock_client:
            client = AsyncMock()
            client.__aenter__.return_value = client
            client.__aexit__.return_value = False
            client.post.return_value = response
            mock_client.return_value = client

            await gateway.brain_list(limit=1)

        client.post.assert_awaited_once_with(
            "/api/v1/memory/find",
            json={"query": None, "limit": 1, "filters": {}, "sort": "updated_at_desc"},
        )

    async def test_brain_list_can_include_test_data_filter(self) -> None:
        gateway = load_gateway_main()
        response = Mock()
        response.is_error = False
        response.json.return_value = []

        with patch("_gateway_src.main._client") as mock_client:
            client = AsyncMock()
            client.__aenter__.return_value = client
            client.__aexit__.return_value = False
            client.post.return_value = response
            mock_client.return_value = client

            await gateway.brain_list(limit=1, include_test_data=True)

        client.post.assert_awaited_once_with(
            "/api/v1/memory/find",
            json={
                "query": None,
                "limit": 1,
                "filters": {"include_test_data": True},
                "sort": "updated_at_desc",
            },
        )

    async def test_brain_search_calls_api_search_path(self) -> None:
        gateway = load_gateway_main()
        response = Mock()
        response.is_error = False
        response.json.return_value = []

        with patch("_gateway_src.main._client") as mock_client:
            client = AsyncMock()
            client.__aenter__.return_value = client
            client.__aexit__.return_value = False
            client.post.return_value = response
            mock_client.return_value = client

            await gateway.brain_search(query="test", top_k=1)

        client.post.assert_awaited_once_with(
            "/api/v1/memory/find",
            json={"query": "test", "limit": 1, "filters": {}},
        )

    async def test_brain_search_can_include_test_data_filter(self) -> None:
        gateway = load_gateway_main()
        response = Mock()
        response.is_error = False
        response.json.return_value = []

        with patch("_gateway_src.main._client") as mock_client:
            client = AsyncMock()
            client.__aenter__.return_value = client
            client.__aexit__.return_value = False
            client.post.return_value = response
            mock_client.return_value = client

            await gateway.brain_search(
                query="test",
                top_k=1,
                include_test_data=True,
            )

        client.post.assert_awaited_once_with(
            "/api/v1/memory/find",
            json={"query": "test", "limit": 1, "filters": {"include_test_data": True}},
        )

    async def test_brain_sync_check_calls_api_sync_check_path_with_json_body(
        self,
    ) -> None:
        gateway = load_gateway_main()
        response = Mock()
        response.is_error = False
        response.json.return_value = {"status": "exists", "message": "Memory exists."}

        with patch("_gateway_src.main._client") as mock_client:
            client = AsyncMock()
            client.__aenter__.return_value = client
            client.__aexit__.return_value = False
            client.post.return_value = response
            mock_client.return_value = client

            await gateway.brain_sync_check(match_key="mk-1")

        client.post.assert_awaited_once_with(
            "/api/v1/memory/sync-check",
            json={
                "memory_id": None,
                "match_key": "mk-1",
                "obsidian_ref": None,
                "file_hash": None,
            },
        )

    async def test_brain_upsert_bulk_calls_bulk_upsert_endpoint(self) -> None:
        gateway = load_gateway_main()
        response = Mock()
        response.is_error = False
        response.json.return_value = {"inserted": [], "updated": [], "skipped": []}

        with patch("_gateway_src.main._client") as mock_client:
            client = AsyncMock()
            client.__aenter__.return_value = client
            client.__aexit__.return_value = False
            client.post.return_value = response
            mock_client.return_value = client

            await gateway.brain_upsert_bulk([{"match_key": "mk-1", "content": "x"}])

        client.post.assert_awaited_once_with(
            "/api/v1/memory/bulk-upsert",
            json=[{"match_key": "mk-1", "content": "x"}],
        )

    async def test_brain_update_uses_canonical_updated_by_placeholder(self) -> None:
        gateway = load_gateway_main()
        response = Mock()
        response.is_error = False
        response.status_code = 200
        response.json.return_value = {
            "id": "mem-1",
            "tenant_id": None,
            "domain": "build",
            "entity_type": "Decision",
            "title": None,
            "summary": None,
            "content": "payload",
            "owner": "",
            "status": "active",
            "version": 1,
            "sensitivity": "internal",
            "superseded_by": None,
            "tags": [],
            "relations": {},
            "obsidian_ref": None,
            "custom_fields": {},
            "content_hash": "hash",
            "match_key": None,
            "previous_id": None,
            "root_id": "mem-1",
            "valid_from": None,
            "created_at": "2026-04-01T00:00:00Z",
            "updated_at": "2026-04-01T00:00:00Z",
            "created_by": "tester",
            "updated_by": "gateway-user",
            "source": None,
            "governance": None,
        }

        with patch("_gateway_src.main._client") as mock_client:
            client = AsyncMock()
            client.__aenter__.return_value = client
            client.__aexit__.return_value = False
            client.patch.return_value = response
            mock_client.return_value = client

            await gateway.brain_update(
                memory_id="mem-1",
                content="payload",
                updated_by="  gateway-user  ",
            )

        client.patch.assert_awaited_once_with(
            "/api/v1/memory/mem-1",
            json={"content": "payload", "updated_by": "agent"},
        )

    async def test_brain_update_empty_updated_by_falls_back_to_agent(self) -> None:
        gateway = load_gateway_main()
        response = Mock()
        response.is_error = False
        response.status_code = 200
        response.json.return_value = {
            "id": "mem-1",
            "tenant_id": None,
            "domain": "build",
            "entity_type": "Decision",
            "title": None,
            "summary": None,
            "content": "payload",
            "owner": "",
            "status": "active",
            "version": 1,
            "sensitivity": "internal",
            "superseded_by": None,
            "tags": [],
            "relations": {},
            "obsidian_ref": None,
            "custom_fields": {},
            "content_hash": "hash",
            "match_key": None,
            "previous_id": None,
            "root_id": "mem-1",
            "valid_from": None,
            "created_at": "2026-04-01T00:00:00Z",
            "updated_at": "2026-04-01T00:00:00Z",
            "created_by": "tester",
            "updated_by": "agent",
            "source": None,
            "governance": None,
        }

        with patch("_gateway_src.main._client") as mock_client:
            client = AsyncMock()
            client.__aenter__.return_value = client
            client.__aexit__.return_value = False
            client.patch.return_value = response
            mock_client.return_value = client

            await gateway.brain_update(
                memory_id="mem-1",
                content="payload",
                updated_by="   ",
            )

        client.patch.assert_awaited_once_with(
            "/api/v1/memory/mem-1",
            json={"content": "payload", "updated_by": "agent"},
        )

    async def test_brain_update_corporate_returns_versioned_record(self) -> None:
        gateway = load_gateway_main()
        response = Mock()
        response.is_error = False
        response.status_code = 200
        response.json.return_value = {
            "id": "corp-2",
            "tenant_id": None,
            "domain": "corporate",
            "entity_type": "Decision",
            "title": None,
            "summary": None,
            "content": "policy v2",
            "owner": "ops@example.com",
            "status": "active",
            "version": 2,
            "sensitivity": "internal",
            "superseded_by": None,
            "tags": ["governance"],
            "relations": {},
            "obsidian_ref": None,
            "custom_fields": {},
            "content_hash": "hash-v2",
            "match_key": "corp:policy:auth",
            "previous_id": "corp-1",
            "root_id": "corp-1",
            "valid_from": None,
            "created_at": "2026-04-01T00:00:00Z",
            "updated_at": "2026-04-01T00:00:00Z",
            "created_by": "tester",
            "updated_by": "admin@example.com",
            "source": None,
            "governance": {"policy_mode": "append_only"},
        }

        with patch("_gateway_src.main._client") as mock_client:
            client = AsyncMock()
            client.__aenter__.return_value = client
            client.__aexit__.return_value = False
            client.patch.return_value = response
            mock_client.return_value = client

            result = await gateway.brain_update(
                memory_id="corp-1",
                content="policy v2",
                updated_by="admin@example.com",
            )

        self.assertEqual(result.domain, "corporate")
        self.assertEqual(result.id, "corp-2")
        self.assertEqual(result.previous_id, "corp-1")
        self.assertEqual(result.root_id, "corp-1")
        self.assertEqual(result.version, 2)
        client.patch.assert_awaited_once_with(
            "/api/v1/memory/corp-1",
            json={"content": "policy v2", "updated_by": "agent"},
        )

    async def test_brain_delete_calls_api_delete_path(self) -> None:
        gateway = load_gateway_main()
        response = Mock()
        response.is_error = False
        response.status_code = 204
        response.json.return_value = {}

        with patch("_gateway_src.main._client") as mock_client:
            client = AsyncMock()
            client.__aenter__.return_value = client
            client.__aexit__.return_value = False
            client.delete.return_value = response
            mock_client.return_value = client

            result = await gateway.brain_delete("mem-1")

        self.assertEqual(result, {"deleted": True, "id": "mem-1"})
        client.delete.assert_awaited_once_with("/api/v1/memory/mem-1")

    async def test_brain_delete_404_raises_not_found(self) -> None:
        gateway = load_gateway_main()
        response = Mock()
        response.is_error = True
        response.status_code = 404
        response.json.return_value = {"detail": "not found"}

        with patch("_gateway_src.main._client") as mock_client:
            client = AsyncMock()
            client.__aenter__.return_value = client
            client.__aexit__.return_value = False
            client.delete.return_value = response
            mock_client.return_value = client

            with self.assertRaisesRegex(ValueError, "Memory not found: mem-1"):
                await gateway.brain_delete("mem-1")

    async def test_brain_delete_403_raises_governance_message(self) -> None:
        gateway = load_gateway_main()
        response = Mock()
        response.is_error = True
        response.status_code = 403
        response.json.return_value = {"detail": "forbidden"}

        with patch("_gateway_src.main._client") as mock_client:
            client = AsyncMock()
            client.__aenter__.return_value = client
            client.__aexit__.return_value = False
            client.delete.return_value = response
            mock_client.return_value = client

            with self.assertRaisesRegex(
                ValueError, "Cannot delete corporate memories. Use deprecation instead."
            ):
                await gateway.brain_delete("mem-1")


if __name__ == "__main__":
    unittest.main()
