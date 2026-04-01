"""
Ollama Embedding Client.
Supports both old (/api/embeddings) and new (/api/embed) Ollama API.
"""
import asyncio
import os

import httpx

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
EMBED_MODEL = os.environ.get("EMBED_MODEL", "nomic-embed-text")
_EMBED_TIMEOUT = httpx.Timeout(30.0)
_EMBED_LIMITS = httpx.Limits(max_connections=20, max_keepalive_connections=10)
_RETRYABLE_STATUS_CODES = {502, 503, 504}

_client: httpx.AsyncClient | None = None


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
    """Fetch an embedding vector for the given text using Ollama."""
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
        return response.json()["embedding"]

    data = response.json()
    # /api/embed returns {"embeddings": [[...]]}
    return data["embeddings"][0]
