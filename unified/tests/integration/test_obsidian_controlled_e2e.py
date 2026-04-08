from __future__ import annotations

import os

import httpx
import pytest


def _enabled() -> bool:
    return os.getenv("RUN_CONTROLLED_OBSIDIAN_E2E", "0").strip() == "1"


@pytest.mark.integration
def test_obsidian_controlled_vault_discovery() -> None:
    if not _enabled():
        pytest.skip("Set RUN_CONTROLLED_OBSIDIAN_E2E=1 to run controlled Obsidian E2E.")

    base_url = os.getenv("OPENBRAIN_BASE_URL", "http://127.0.0.1:7010")
    internal_key = os.getenv("INTERNAL_API_KEY", "")
    expected_vault = os.getenv("OBSIDIAN_TEST_VAULT", "").strip()

    headers: dict[str, str] = {}
    if internal_key:
        headers["X-Internal-Key"] = internal_key

    with httpx.Client(base_url=base_url, timeout=15.0, headers=headers) as client:
        resp = client.get("/api/v1/obsidian/vaults")

    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert isinstance(payload, list)
    if expected_vault:
        assert expected_vault in payload
