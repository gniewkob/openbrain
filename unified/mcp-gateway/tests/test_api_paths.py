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

        with patch("_gateway_src.main._client") as mock_client, patch.object(
            gateway, "MCP_SOURCE_SYSTEM", "codex"
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

    async def test_brain_list_calls_api_memories_path(self) -> None:
        gateway = load_gateway_main()
        response = Mock()
        response.is_error = False
        response.json.return_value = []

        with patch("_gateway_src.main._client") as mock_client:
            client = AsyncMock()
            client.__aenter__.return_value = client
            client.__aexit__.return_value = False
            client.get.return_value = response
            mock_client.return_value = client

            await gateway.brain_list(limit=1)

        client.get.assert_awaited_once_with("/api/memories", params={"limit": 1})

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

    async def test_brain_sync_check_calls_api_sync_check_path_with_json_body(self) -> None:
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
            "/api/memories/sync-check",
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
            "/api/memories/bulk-upsert",
            json=[{"match_key": "mk-1", "content": "x"}],
        )


if __name__ == "__main__":
    unittest.main()
