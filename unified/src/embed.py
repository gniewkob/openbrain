"""
Ollama Embedding Client.
Supports both old (/api/embeddings) and new (/api/embed) Ollama API.
Includes LRU caching for embeddings to reduce redundant API calls.
Includes a circuit breaker to fail fast when Ollama is repeatedly unavailable.
"""

import asyncio
import time as _time
from collections import OrderedDict

import httpx
import structlog

from .config import get_config

# These will be initialized lazily from config
_EMBED_TIMEOUT = httpx.Timeout(5.0)
_EMBED_LIMITS = httpx.Limits(max_connections=100, max_keepalive_connections=20)
_RETRYABLE_STATUS_CODES = {502, 503, 504}

# Ollama nomic-embed-text supports up to 8192 tokens; ~4 chars/token → 6000 char
# safe limit. We truncate instead of failing so writes always succeed.
EMBED_MAX_CHARS = 6_000

log = structlog.get_logger()

_client: httpx.AsyncClient | None = None

# LRU cache: OrderedDict preserves insertion order; move_to_end on hit = true LRU
_embedding_cache: OrderedDict[str, tuple[tuple[float, ...], str]] = OrderedDict()
_embedding_cache_lock = asyncio.Lock()


# ---------------------------------------------------------------------------
# Circuit breaker for Ollama (audit 4.1)
# ---------------------------------------------------------------------------


class CircuitOpenError(RuntimeError):
    """Raised when the Ollama circuit breaker is open (service unavailable)."""


class _CircuitBreaker:
    """Three-state circuit breaker: closed → open → half_open → closed.

    Trips after `failure_threshold` consecutive network failures.
    Allows a probe after `reset_timeout` seconds (half_open state).
    """

    def __init__(self, failure_threshold: int = 3, reset_timeout: float = 30.0) -> None:
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self._state = "closed"
        self._failures = 0
        self._opened_at: float = 0.0

    @property
    def state(self) -> str:
        return self._state

    def reset(self) -> None:
        self._state = "closed"
        self._failures = 0
        self._opened_at = 0.0

    async def guard(self) -> None:
        """Raise CircuitOpenError if circuit is open and reset_timeout not elapsed."""
        if self._state == "closed":
            return
        if self._state == "open":
            if _time.monotonic() - self._opened_at >= self.reset_timeout:
                self._state = "half_open"
                return
            raise CircuitOpenError(
                "Ollama embedding service is unavailable (circuit open). "
                "Retry after a moment."
            )
        # half_open: allow one probe through

    def on_success(self) -> None:
        self._failures = 0
        self._state = "closed"

    def on_failure(self) -> None:
        self._failures += 1
        if self._failures >= self.failure_threshold:
            self._state = "open"
            self._opened_at = _time.monotonic()


_circuit_breaker = _CircuitBreaker()


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
    """Close the embedding HTTP client and cleanup resources."""
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
    Truncates text to EMBED_MAX_CHARS before embedding.
    Uses LRU cache to avoid redundant API calls for identical text.
    Raises CircuitOpenError if Ollama is repeatedly unavailable.
    """
    if len(text) > EMBED_MAX_CHARS:
        log.warning(
            "embed_text_truncated",
            original_len=len(text),
            truncated_to=EMBED_MAX_CHARS,
        )
        text = text[:EMBED_MAX_CHARS]

    config = get_config()
    text_hash = _compute_text_hash(text)

    # Check the OrderedDict cache under lock to prevent races
    async with _embedding_cache_lock:
        if text_hash in _embedding_cache:
            embedding, cached_model = _embedding_cache[text_hash]
            if cached_model == config.embedding.model:
                _embedding_cache.move_to_end(text_hash)
                return list(embedding)
            # Model changed — evict stale entry so fresh embedding is computed
            del _embedding_cache[text_hash]

    # Check circuit breaker before making an HTTP call to Ollama
    await _circuit_breaker.guard()

    # Cache miss — call Ollama
    try:
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
    except (httpx.ConnectError, httpx.TimeoutException):
        _circuit_breaker.on_failure()
        raise
    else:
        _circuit_breaker.on_success()

    await _update_embedding_cache(text_hash, tuple(result), config.embedding.model)

    return result


async def _update_embedding_cache(
    text_hash: str, embedding: tuple[float, ...], model: str
) -> None:
    """Update the embedding cache with a new entry (true LRU eviction)."""
    config = get_config()
    async with _embedding_cache_lock:
        if text_hash in _embedding_cache:
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
