from __future__ import annotations

import importlib
import sys
import unittest
from unittest.mock import AsyncMock, patch

import httpx


EMBED_MODULE = "src.embed"


def _reload_embed_module():
    sys.modules.pop(EMBED_MODULE, None)
    return importlib.import_module(EMBED_MODULE)


class EmbedClientTests(unittest.IsolatedAsyncioTestCase):
    async def asyncTearDown(self) -> None:
        if EMBED_MODULE in sys.modules:
            embed = sys.modules[EMBED_MODULE]
            await embed.close_embedding_client()

    async def test_reuses_single_async_client(self) -> None:
        embed = _reload_embed_module()
        fake_client = AsyncMock()

        with patch.object(embed.httpx, "AsyncClient", return_value=fake_client) as factory:
            client_one = embed._get_client()
            client_two = embed._get_client()

        self.assertIs(client_one, fake_client)
        self.assertIs(client_two, fake_client)
        factory.assert_called_once()

    async def test_falls_back_to_legacy_endpoint_on_404(self) -> None:
        embed = _reload_embed_module()
        client = AsyncMock()
        client.post.side_effect = [
            httpx.Response(404, request=httpx.Request("POST", "http://test/api/embed")),
            httpx.Response(200, json={"embedding": [0.1, 0.2]}, request=httpx.Request("POST", "http://test/api/embeddings")),
        ]

        with patch.object(embed, "_get_client", return_value=client):
            result = await embed.get_embedding("hello")

        self.assertEqual(result, [0.1, 0.2])
        self.assertEqual(client.post.await_count, 2)

    async def test_retries_retryable_transport_error(self) -> None:
        embed = _reload_embed_module()
        client = AsyncMock()
        client.post.side_effect = [
            httpx.ConnectError("boom", request=httpx.Request("POST", "http://test/api/embed")),
            httpx.Response(200, json={"embeddings": [[0.3, 0.4]]}, request=httpx.Request("POST", "http://test/api/embed")),
        ]

        with patch.object(embed, "_get_client", return_value=client), patch.object(embed.asyncio, "sleep", new=AsyncMock()):
            result = await embed.get_embedding("hello")

        self.assertEqual(result, [0.3, 0.4])
        self.assertEqual(client.post.await_count, 2)
