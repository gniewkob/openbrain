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

        with patch.object(
            embed.httpx, "AsyncClient", return_value=fake_client
        ) as factory:
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
            httpx.Response(
                200,
                json={"embedding": [0.1, 0.2]},
                request=httpx.Request("POST", "http://test/api/embeddings"),
            ),
        ]

        with patch.object(embed, "_get_client", return_value=client):
            result = await embed.get_embedding("hello")

        self.assertEqual(result, [0.1, 0.2])
        self.assertEqual(client.post.await_count, 2)

    async def test_retries_retryable_transport_error(self) -> None:
        embed = _reload_embed_module()
        client = AsyncMock()
        client.post.side_effect = [
            httpx.ConnectError(
                "boom", request=httpx.Request("POST", "http://test/api/embed")
            ),
            httpx.Response(
                200,
                json={"embeddings": [[0.3, 0.4]]},
                request=httpx.Request("POST", "http://test/api/embed"),
            ),
        ]

        with (
            patch.object(embed, "_get_client", return_value=client),
            patch.object(embed.asyncio, "sleep", new=AsyncMock()),
        ):
            result = await embed.get_embedding("hello")

        self.assertEqual(result, [0.3, 0.4])
        self.assertEqual(client.post.await_count, 2)

    async def test_truncates_long_text_before_embedding(self) -> None:
        """Text longer than EMBED_MAX_CHARS is truncated, not passed as-is."""
        embed = _reload_embed_module()
        client = AsyncMock()
        client.post.return_value = httpx.Response(
            200,
            json={"embeddings": [[0.5, 0.6]]},
            request=httpx.Request("POST", "http://test/api/embed"),
        )
        long_text = "x" * (embed.EMBED_MAX_CHARS + 500)

        with patch.object(embed, "_get_client", return_value=client):
            result = await embed.get_embedding(long_text)

        self.assertEqual(result, [0.5, 0.6])
        # The text sent to Ollama must be at most EMBED_MAX_CHARS
        sent_payload = client.post.call_args[1]["json"]
        sent_text = sent_payload.get("input") or sent_payload.get("prompt", "")
        self.assertLessEqual(len(sent_text), embed.EMBED_MAX_CHARS)

    async def test_short_text_not_truncated(self) -> None:
        """Text within the limit is passed unchanged."""
        embed = _reload_embed_module()
        client = AsyncMock()
        client.post.return_value = httpx.Response(
            200,
            json={"embeddings": [[0.7, 0.8]]},
            request=httpx.Request("POST", "http://test/api/embed"),
        )
        short_text = "hello world"

        with patch.object(embed, "_get_client", return_value=client):
            await embed.get_embedding(short_text)

        sent_payload = client.post.call_args[1]["json"]
        sent_text = sent_payload.get("input") or sent_payload.get("prompt", "")
        self.assertEqual(sent_text, short_text)

    async def test_retry_on_retryable_status_code(self) -> None:
        """503 on attempt 0 → retry; 200 on attempt 1 → success (lines 142-143)."""
        embed = _reload_embed_module()
        client = AsyncMock()
        client.post.side_effect = [
            httpx.Response(
                503,
                request=httpx.Request("POST", "http://test/api/embed"),
            ),
            httpx.Response(
                200,
                json={"embeddings": [[0.9, 1.0]]},
                request=httpx.Request("POST", "http://test/api/embed"),
            ),
        ]

        with (
            patch.object(embed, "_get_client", return_value=client),
            patch.object(embed.asyncio, "sleep", new=AsyncMock()),
        ):
            result = await embed.get_embedding("retry-test")

        self.assertEqual(result, [0.9, 1.0])
        self.assertEqual(client.post.await_count, 2)

    async def test_raises_after_all_http_error_attempts(self) -> None:
        """3 consecutive httpx.ConnectError → raises on 3rd attempt (line 135)."""
        embed = _reload_embed_module()
        client = AsyncMock()
        error = httpx.ConnectError(
            "boom", request=httpx.Request("POST", "http://test/api/embed")
        )
        client.post.side_effect = [error, error, error]

        with (
            patch.object(embed, "_get_client", return_value=client),
            patch.object(embed.asyncio, "sleep", new=AsyncMock()),
        ):
            with self.assertRaises(httpx.ConnectError):
                await embed.get_embedding("fail-all")

        self.assertEqual(client.post.await_count, 3)

    async def test_update_cache_updates_existing_entry(self) -> None:
        """_update_embedding_cache with existing hash → move_to_end path (lines 216-218)."""
        embed = _reload_embed_module()
        await embed.clear_embedding_cache()

        text_hash = "abcdef1234567890abcdef1234567890"
        embed._embedding_cache[text_hash] = ((0.1, 0.2), "model-a")

        with patch("src.embed.get_config") as mock_cfg:
            mock_cfg.return_value.embedding.cache_size = 128
            await embed._update_embedding_cache(text_hash, (0.3, 0.4), "model-a")

        assert embed._embedding_cache[text_hash] == ((0.3, 0.4), "model-a")

    async def test_update_cache_evicts_lru_when_full(self) -> None:
        """Cache at capacity → popitem evicts LRU entry (line 221)."""
        embed = _reload_embed_module()
        await embed.clear_embedding_cache()

        # Fill cache to capacity (2 entries)
        embed._embedding_cache["key1"] = ((1.0,), "model-x")
        embed._embedding_cache["key2"] = ((2.0,), "model-x")

        with patch("src.embed.get_config") as mock_cfg:
            mock_cfg.return_value.embedding.cache_size = 2
            await embed._update_embedding_cache("key3", (3.0,), "model-x")

        # key1 (LRU) should have been evicted
        assert "key1" not in embed._embedding_cache
        assert "key3" in embed._embedding_cache

    async def test_get_cache_stats_returns_sizes(self) -> None:
        """get_cache_stats returns cache_size and cache_limit (lines 227-229)."""
        embed = _reload_embed_module()
        await embed.clear_embedding_cache()
        embed._embedding_cache["h1"] = ((1.0,), "m")

        with patch("src.embed.get_config") as mock_cfg:
            mock_cfg.return_value.embedding.cache_size = 64
            stats = await embed.get_cache_stats()

        assert stats["cache_size"] == 1
        assert stats["cache_limit"] == 64

    async def test_cache_invalidated_when_model_changes(self) -> None:
        """Cached entry with old model name is evicted and Ollama is called again."""
        embed = _reload_embed_module()
        await embed.clear_embedding_cache()

        client = AsyncMock()
        client.post.return_value = httpx.Response(
            200,
            json={"embeddings": [[1.0, 2.0]]},
            request=httpx.Request("POST", "http://test/api/embed"),
        )

        with patch.object(embed, "_get_client", return_value=client):
            # First call — model A
            with patch("src.embed.get_config") as mock_cfg:
                mock_cfg.return_value.embedding.model = "model-a"
                mock_cfg.return_value.embedding.cache_size = 128
                mock_cfg.return_value.embedding.url = "http://localhost:11434"
                await embed.get_embedding("hello")

            self.assertEqual(client.post.await_count, 1)

            # Second call — model B (same text, different model)
            with patch("src.embed.get_config") as mock_cfg:
                mock_cfg.return_value.embedding.model = "model-b"
                mock_cfg.return_value.embedding.cache_size = 128
                mock_cfg.return_value.embedding.url = "http://localhost:11434"
                await embed.get_embedding("hello")

            # Must call Ollama again (cache miss due to model change)
            self.assertEqual(client.post.await_count, 2)
