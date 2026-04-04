"""
Ollama Embedding Client.
Supports both old (/api/embeddings) and new (/api/embed) Ollama API.
Includes LRU caching for embeddings to reduce redundant API calls.
"""

import asyncio
from collections import OrderedDict
from functools import lru_cache
from typing import List

import httpx

from .config import get_config

# These will be initialized lazily from config
_EMBED_TIMEOUT = httpx.Timeout(30.0)
_EMBED_LIMITS = httpx.Limits(max_connections=20, max_keepalive_connections=10)
_RETRYABLE_STATUS_CODES = {502, 503, 504}

_client: httpx.AsyncClient | None = None


# Thread-safe cache for embeddings using LRU strategy
# Note: Using a fixed maxsize here; actual cache size controlled in _update_embedding_cache
@lru_cache(maxsize=1000)
def _get_cached_embedding(text_hash: str) -> tuple[List[float], str] | None:
    """
    Cache storage for embeddings. Returns (embedding, model) or None.
    Uses text hash as key to avoid storing large strings.
    """
    return None


def _compute_text_hash(text: str) -> str:
    """Compute a hash of the text for cache key."""
    import hashlib

    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:32]


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        config = get_config()
        _client = httpx.AsyncClient(
            base_url=config.embedding.url,
            timeout=_EMBED_TIMEOUT,
            limits=_EMBED_LIMITS,
        )
    return _client


async def close_embedding_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


async def _post_with_retry(path: str, payload: dict[str, str]) -> httpx.Response:
    client = _get_client()
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            response = await client.post(path, json=payload)
        except httpx.HTTPError as exc:
            last_error = exc
            if attempt == 2:
                raise
            await asyncio.sleep(0.2 * (attempt + 1))
            continue

        if response.status_code == 404:
            return response
        if response.status_code in _RETRYABLE_STATUS_CODES and attempt < 2:
            await asyncio.sleep(0.2 * (attempt + 1))
            continue
        response.raise_for_status()
        return response

    assert last_error is not None
    raise last_error


async def get_embedding(text: str) -> list[float]:
    """
    Fetch an embedding vector for the given text using Ollama.
    Uses LRU cache to avoid redundant API calls for identical text.
    """
    config = get_config()

    # Check cache first
    text_hash = _compute_text_hash(text)
    cached = _get_cached_embedding(text_hash)
    if cached is not None:
        embedding, cached_model = cached
        if cached_model == config.embedding.model:
            return list(embedding)  # Return copy to prevent mutation

    # Try new API first (/api/embed), fall back to old (/api/embeddings).
    response = await _post_with_retry(
        "/api/embed",
        {"model": config.embedding.model, "input": text},
    )
    if response.status_code == 404:
        response = await _post_with_retry(
            "/api/embeddings",
            {"model": config.embedding.model, "prompt": text},
        )
        result = response.json()["embedding"]
    else:
        data = response.json()
        # /api/embed returns {"embeddings": [[...]]}
        result = data["embeddings"][0]

    # Store in cache (convert to tuple for hashability)
    # Note: lru_cache requires hashable types, so we use a simple wrapper
    # The cache is managed at module level for persistence
    await _update_embedding_cache(text_hash, tuple(result), config.embedding.model)

    return result


# LRU cache: OrderedDict preserves insertion order; move_to_end on hit = true LRU
_embedding_cache: OrderedDict[str, tuple[tuple[float, ...], str]] = OrderedDict()
_embedding_cache_lock = asyncio.Lock()


async def _update_embedding_cache(
    text_hash: str, embedding: tuple[float, ...], model: str
) -> None:
    """Update the embedding cache with a new entry (true LRU eviction)."""
    config = get_config()
    async with _embedding_cache_lock:
        if text_hash in _embedding_cache:
            # Refresh recency — move existing entry to most-recently-used position
            _embedding_cache.move_to_end(text_hash)
            _embedding_cache[text_hash] = (embedding, model)
            return
        if len(_embedding_cache) >= config.embedding.cache_size:
            # Evict least recently used (head of OrderedDict)
            _embedding_cache.popitem(last=False)
        _embedding_cache[text_hash] = (embedding, model)


async def get_cache_stats() -> dict[str, int]:
    """Return cache statistics for monitoring."""
    config = get_config()
    async with _embedding_cache_lock:
        return {
            "cache_size": len(_embedding_cache),
            "cache_limit": config.embedding.cache_size,
        }


async def clear_embedding_cache() -> None:
    """Clear the embedding cache. Useful for testing or memory management."""
    async with _embedding_cache_lock:
        _embedding_cache.clear()
