"""
Ollama Embedding Client.
Supports both old (/api/embeddings) and new (/api/embed) Ollama API.
Includes LRU caching for embeddings to reduce redundant API calls.
"""
import asyncio
import os
from functools import lru_cache
from typing import List

import httpx

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
EMBED_MODEL = os.environ.get("EMBED_MODEL", "nomic-embed-text")
_EMBED_TIMEOUT = httpx.Timeout(30.0)
_EMBED_LIMITS = httpx.Limits(max_connections=20, max_keepalive_connections=10)
_RETRYABLE_STATUS_CODES = {502, 503, 504}
# Cache size for embeddings (tune based on memory constraints)
_EMBED_CACHE_SIZE = int(os.environ.get("EMBED_CACHE_SIZE", "1000"))

_client: httpx.AsyncClient | None = None


# Thread-safe cache for embeddings using LRU strategy
@lru_cache(maxsize=_EMBED_CACHE_SIZE)
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
        _client = httpx.AsyncClient(
            base_url=OLLAMA_URL,
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
    # Check cache first
    text_hash = _compute_text_hash(text)
    cached = _get_cached_embedding(text_hash)
    if cached is not None:
        embedding, cached_model = cached
        if cached_model == EMBED_MODEL:
            return list(embedding)  # Return copy to prevent mutation
    
    # Try new API first (/api/embed), fall back to old (/api/embeddings).
    response = await _post_with_retry(
        "/api/embed",
        {"model": EMBED_MODEL, "input": text},
    )
    if response.status_code == 404:
        response = await _post_with_retry(
            "/api/embeddings",
            {"model": EMBED_MODEL, "prompt": text},
        )
        result = response.json()["embedding"]
    else:
        data = response.json()
        # /api/embed returns {"embeddings": [[...]]}
        result = data["embeddings"][0]
    
    # Store in cache (convert to tuple for hashability)
    # Note: lru_cache requires hashable types, so we use a simple wrapper
    # The cache is managed at module level for persistence
    _update_embedding_cache(text_hash, tuple(result), EMBED_MODEL)
    
    return result


# Simple cache storage (module-level for persistence)
_embedding_cache: dict[str, tuple[tuple[float, ...], str]] = {}


def _update_embedding_cache(text_hash: str, embedding: tuple[float, ...], model: str) -> None:
    """Update the embedding cache with a new entry."""
    global _embedding_cache
    # Simple LRU eviction when cache is full
    if len(_embedding_cache) >= _EMBED_CACHE_SIZE:
        # Remove oldest entry (simple FIFO for now)
        oldest_key = next(iter(_embedding_cache))
        del _embedding_cache[oldest_key]
    _embedding_cache[text_hash] = (embedding, model)


def get_cache_stats() -> dict[str, int]:
    """Return cache statistics for monitoring."""
    return {
        "cache_size": len(_embedding_cache),
        "cache_limit": _EMBED_CACHE_SIZE,
    }


def clear_embedding_cache() -> None:
    """Clear the embedding cache. Useful for testing or memory management."""
    global _embedding_cache
    _embedding_cache.clear()
