import importlib
import unittest
from unittest.mock import AsyncMock, Mock, patch


class GatewayApiPathTests(unittest.IsolatedAsyncioTestCase):
    async def test_brain_list_calls_api_memories_path(self) -> None:
        gateway = importlib.import_module("src.main")
        response = Mock()
        response.is_error = False
        response.json.return_value = []

        with patch("src.main._client") as mock_client:
            client = AsyncMock()
            client.__aenter__.return_value = client
            client.__aexit__.return_value = False
            client.get.return_value = response
            mock_client.return_value = client

            await gateway.brain_list(limit=1)

        client.get.assert_awaited_once_with("/api/memories", params={"limit": 1})

    async def test_brain_search_calls_api_search_path(self) -> None:
        gateway = importlib.import_module("src.main")
        response = Mock()
        response.is_error = False
        response.json.return_value = []

        with patch("src.main._client") as mock_client:
            client = AsyncMock()
            client.__aenter__.return_value = client
            client.__aexit__.return_value = False
            client.post.return_value = response
            mock_client.return_value = client

            await gateway.brain_search(query="test", top_k=1)

        client.post.assert_awaited_once_with(
            "/api/memories/search",
            json={"query": "test", "top_k": 1, "filters": {}},
        )


if __name__ == "__main__":
    unittest.main()
