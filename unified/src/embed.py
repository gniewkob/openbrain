"""
Ollama Embedding Client.
Supports both old (/api/embeddings) and new (/api/embed) Ollama API.
"""
import os

import httpx

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
EMBED_MODEL = os.environ.get("EMBED_MODEL", "nomic-embed-text")


async def get_embedding(text: str) -> list[float]:
    """Fetch an embedding vector for the given text using Ollama."""
    async with httpx.AsyncClient(base_url=OLLAMA_URL, timeout=30.0) as client:
        # Try new API first (/api/embed), fall back to old (/api/embeddings)
        response = await client.post(
            "/api/embed",
            json={"model": EMBED_MODEL, "input": text},
        )
        if response.status_code == 404:
            response = await client.post(
                "/api/embeddings",
                json={"model": EMBED_MODEL, "prompt": text},
            )
            response.raise_for_status()
            return response.json()["embedding"]

        response.raise_for_status()
        data = response.json()
        # /api/embed returns {"embeddings": [[...]]}
        return data["embeddings"][0]
