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


@pytest.mark.integration
def test_obsidian_controlled_note_roundtrip() -> None:
    if not _enabled():
        pytest.skip("Set RUN_CONTROLLED_OBSIDIAN_E2E=1 to run controlled Obsidian E2E.")

    base_url = os.getenv("OPENBRAIN_BASE_URL", "http://127.0.0.1:7010")
    internal_key = os.getenv("INTERNAL_API_KEY", "")
    vault = os.getenv("OBSIDIAN_TEST_VAULT", "").strip() or "Documents"
    note_path = os.getenv(
        "OBSIDIAN_TEST_NOTE_PATH", "OpenBrain Controlled E2E/roundtrip.md"
    ).strip()

    headers: dict[str, str] = {}
    if internal_key:
        headers["X-Internal-Key"] = internal_key

    write_payload = {
        "vault": vault,
        "path": note_path,
        "content": "# Controlled E2E\n\nRoundtrip validation",
        "frontmatter": {"domain": "build", "entity_type": "Architecture"},
        "overwrite": True,
    }

    with httpx.Client(base_url=base_url, timeout=20.0, headers=headers) as client:
        write_resp = client.post("/api/v1/obsidian/write-note", json=write_payload)
        assert write_resp.status_code == 200, write_resp.text

        read_resp = client.post(
            "/api/v1/obsidian/read-note", json={"vault": vault, "path": note_path}
        )
        assert read_resp.status_code == 200, read_resp.text

        sync_resp = client.post(
            "/api/v1/obsidian/sync",
            json={
                "vault": vault,
                "paths": [note_path],
                "domain": "build",
                "entity_type": "Architecture",
                "owner": "controlled-e2e",
                "tags": ["controlled-e2e"],
            },
        )
        assert sync_resp.status_code == 200, sync_resp.text

    read_payload = read_resp.json()
    assert read_payload["path"] == note_path
    assert "Controlled E2E" in read_payload["content"]

    sync_payload = sync_resp.json()
    assert sync_payload["resolved_paths"] == [note_path]
    assert sync_payload["scanned"] == 1
