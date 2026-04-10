from __future__ import annotations

import os
import time

import pytest
import httpx

from src import mcp_transport


pytestmark = pytest.mark.skipif(
    os.environ.get("OPENBRAIN_RUN_LIVE_SMOKE") != "1",
    reason="Set OPENBRAIN_RUN_LIVE_SMOKE=1 to run live transport smoke tests.",
)


@pytest.mark.asyncio
async def test_live_transport_store_get_delete_roundtrip() -> None:
    """Live smoke: verify CRUD roundtrip via transport layer against running backend."""
    base_url = os.environ.get("OPENBRAIN_LIVE_URL", "http://127.0.0.1:7010").rstrip("/")
    mcp_transport.BRAIN_URL = base_url

    internal_key = os.environ.get("INTERNAL_API_KEY", "").strip()
    if internal_key:
        mcp_transport.INTERNAL_API_KEY = internal_key

    healthz_url = f"{base_url}/healthz"
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            probe = await client.get(healthz_url)
    except Exception as exc:  # pragma: no cover - diagnostic path
        pytest.skip(f"Live backend unreachable ({healthz_url}): {exc}")
    if probe.status_code != 200:
        pytest.skip(f"Live backend not ready ({healthz_url} -> {probe.status_code})")

    match_key = f"smoke:live:transport:{int(time.time())}"
    created = await mcp_transport.brain_store(
        content="live smoke test for transport CRUD",
        domain="build",
        entity_type="Note",
        title="Live Smoke CRUD",
        tags=["smoke", "live", "transport"],
        match_key=match_key,
    )
    memory_id = created["id"]

    fetched = await mcp_transport.brain_get(memory_id)
    assert fetched["id"] == memory_id
    assert fetched.get("match_key") == match_key

    deleted = await mcp_transport.brain_delete(memory_id)
    assert deleted["deleted"] is True
    assert deleted["id"] == memory_id
