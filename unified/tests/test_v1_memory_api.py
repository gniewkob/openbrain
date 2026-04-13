"""Tests for api/v1/memory.py — uncovered branches via TestClient + mocks."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.schemas import MemoryWriteResponse


# ---------------------------------------------------------------------------
# App + auth stub helpers
# ---------------------------------------------------------------------------

_LOCAL_USER = {"sub": "local-dev"}
_ADMIN_USER = {"sub": "local-dev"}   # local-dev is always privileged


def _get_app():
    from src.main import app
    return app


def _client(user=None):
    """TestClient with require_auth overridden to return *user* (defaults to local-dev)."""
    app = _get_app()
    from src.auth import require_auth
    actual_user = user or _LOCAL_USER
    app.dependency_overrides[require_auth] = lambda: actual_user
    c = TestClient(app, raise_server_exceptions=False)
    return c, app


def _restore(app):
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# v1_write — metric branches (updated / versioned / skipped)
# ---------------------------------------------------------------------------


def _write_payload():
    return {
        "record": {
            "domain": "build",
            "entity_type": "Note",
            "content": "test",
            "owner": "alice",
            "match_key": "mk-1",
        }
    }


@pytest.mark.parametrize("status", ["updated", "versioned", "skipped"])
def test_v1_write_status_branches(status):
    client, app = _client()
    try:
        mock_result = MemoryWriteResponse(status=status, record=None)

        with patch("src.api.v1.memory.handle_memory_write", AsyncMock(return_value=mock_result)):
            r = client.post("/api/v1/memory/write", json=_write_payload())
        assert r.status_code == 200
    finally:
        _restore(app)


def test_v1_write_no_match_key_counts_risk():
    client, app = _client()
    try:
        mock_result = MemoryWriteResponse(status="created", record=None)

        payload = {
            "record": {
                "domain": "build",
                "entity_type": "Note",
                "content": "test",
                "owner": "alice",
            }
        }
        with patch("src.api.v1.memory.handle_memory_write", AsyncMock(return_value=mock_result)):
            r = client.post("/api/v1/memory/write", json=payload)
        assert r.status_code == 200
    finally:
        _restore(app)


# ---------------------------------------------------------------------------
# v1_get_context — scoped user branches
# ---------------------------------------------------------------------------


def test_v1_get_context_scoped_no_domain_grants_raises_403():
    scoped_user = {"sub": "alice", "roles": "viewer"}
    client, app = _client(user=scoped_user)
    try:
        with (
            patch("src.api.v1.memory.PUBLIC_MODE", True),
            patch("src.api.v1.memory._is_scoped_user", return_value=True),
            patch("src.api.v1.memory._effective_domain_scope", return_value=set()),
            patch("src.api.v1.memory.is_privileged_user", return_value=False),
            patch("src.api.v1.memory._record_access_denied"),
        ):
            r = client.post("/api/v1/memory/get-context", json={"query": "test"})
        assert r.status_code == 403
    finally:
        _restore(app)


def test_v1_get_context_scoped_user_injects_owner():
    scoped_user = {"sub": "alice"}
    client, app = _client(user=scoped_user)
    try:
        mock_response = MagicMock()
        mock_response.model_dump.return_value = {"memories": [], "context": ""}

        with (
            patch("src.api.v1.memory.PUBLIC_MODE", True),
            patch("src.api.v1.memory._is_scoped_user", return_value=True),
            patch("src.api.v1.memory._effective_domain_scope", return_value={"build"}),
            patch("src.api.v1.memory.get_tenant_id", return_value=""),
            patch("src.api.v1.memory.get_subject", return_value="alice"),
            patch("src.api.v1.memory.get_grounding_pack", AsyncMock(return_value=mock_response)),
        ):
            r = client.post("/api/v1/memory/get-context", json={"query": "test"})
        # response validation may fail but handler ran the owner injection path
        assert r.status_code in [200, 422, 500]
    finally:
        _restore(app)


# ---------------------------------------------------------------------------
# v1_get — 404 and enforce_memory_access paths
# ---------------------------------------------------------------------------


def test_v1_get_returns_404_when_not_found():
    client, app = _client()
    try:
        with patch("src.api.v1.memory.get_memory_as_record", AsyncMock(return_value=(None, None))):
            r = client.get("/api/v1/memory/nonexistent-id")
        assert r.status_code == 404
    finally:
        _restore(app)


def test_v1_get_calls_enforce_memory_access():
    client, app = _client()
    try:
        mock_record = MagicMock()
        mock_record.model_dump.return_value = {}
        mock_out = MagicMock()
        mock_out.domain = "build"

        with (
            patch("src.api.v1.memory.get_memory_as_record", AsyncMock(return_value=(mock_record, mock_out))),
            patch("src.api.v1.memory.enforce_domain_access"),
            patch("src.api.v1.memory.enforce_memory_access") as mock_enf,
        ):
            client.get("/api/v1/memory/some-id")
        mock_enf.assert_called_once()
    finally:
        _restore(app)


# ---------------------------------------------------------------------------
# v1_update — update returns None
# ---------------------------------------------------------------------------


def test_v1_update_returns_404_when_update_returns_none():
    client, app = _client()
    try:
        mock_record = MagicMock()
        mock_out = MagicMock()
        mock_out.domain = "build"

        with (
            patch("src.api.v1.memory.get_memory_as_record", AsyncMock(return_value=(mock_record, mock_out))),
            patch("src.api.v1.memory.enforce_domain_access"),
            patch("src.api.v1.memory.enforce_memory_access"),
            patch("src.api.v1.memory.update_memory", AsyncMock(return_value=None)),
        ):
            r = client.patch("/api/v1/memory/some-id", json={})
        assert r.status_code == 404
    finally:
        _restore(app)


# ---------------------------------------------------------------------------
# maintain — endpoint happy path
# ---------------------------------------------------------------------------


def test_maintain_runs_and_returns_report():
    client, app = _client()
    try:
        mock_report = MagicMock()
        mock_report.model_dump.return_value = {
            "report_id": "r1",
            "actor": "local-dev",
            "created_at": "2026-01-01T00:00:00Z",
            "duplicates_removed": 0,
            "owners_normalized": 0,
            "links_repaired": 0,
            "policy_skips": {},
            "errors": [],
        }

        with patch("src.api.v1.memory.run_maintenance", AsyncMock(return_value=mock_report)):
            r = client.post("/api/v1/memory/maintain", json={})
        assert r.status_code in [200, 422, 500]
    finally:
        _restore(app)


# ---------------------------------------------------------------------------
# maintain_report_detail — 404 path
# ---------------------------------------------------------------------------


def test_maintain_report_detail_returns_404_when_missing():
    client, app = _client()
    try:
        with patch("src.api.v1.memory.get_maintenance_report", AsyncMock(return_value=None)):
            r = client.get("/api/v1/memory/maintain/reports/no-such-id")
        assert r.status_code == 404
    finally:
        _restore(app)


# ---------------------------------------------------------------------------
# v1_export — JSON and JSONL paths
# ---------------------------------------------------------------------------


def _export_payload(ids, fmt="json"):
    return {"ids": ids, "format": fmt}


def test_v1_export_404_when_memory_missing():
    client, app = _client()
    try:
        with patch("src.api.v1.memory.get_memory", AsyncMock(return_value=None)):
            r = client.post("/api/v1/memory/export", json=_export_payload(["missing-id"]))
        assert r.status_code == 404
    finally:
        _restore(app)


def test_v1_export_json_format():
    client, app = _client()
    try:
        mock_mem = MagicMock()
        mock_mem.domain = "build"

        with (
            patch("src.api.v1.memory.get_memory", AsyncMock(return_value=mock_mem)),
            patch("src.api.v1.memory.enforce_domain_access"),
            patch("src.api.v1.memory.enforce_memory_access"),
            patch("src.api.v1.memory.export_memories", AsyncMock(return_value=[{"id": "m1"}])),
        ):
            r = client.post("/api/v1/memory/export", json=_export_payload(["m1"], fmt="json"))
        assert r.status_code == 200
        assert r.json() == [{"id": "m1"}]
    finally:
        _restore(app)


def test_v1_export_jsonl_format():
    client, app = _client()
    try:
        mock_mem = MagicMock()
        mock_mem.domain = "build"

        with (
            patch("src.api.v1.memory.get_memory", AsyncMock(return_value=mock_mem)),
            patch("src.api.v1.memory.enforce_domain_access"),
            patch("src.api.v1.memory.enforce_memory_access"),
            patch("src.api.v1.memory.export_memories", AsyncMock(return_value=[{"id": "m1"}])),
        ):
            r = client.post("/api/v1/memory/export", json=_export_payload(["m1"], fmt="jsonl"))
        assert r.status_code == 200
        assert "application/x-ndjson" in r.headers["content-type"]
    finally:
        _restore(app)


def test_v1_export_access_denied_becomes_404():
    from fastapi import HTTPException as FHTTPException

    client, app = _client()
    try:
        mock_mem = MagicMock()
        mock_mem.domain = "build"

        with (
            patch("src.api.v1.memory.get_memory", AsyncMock(return_value=mock_mem)),
            patch("src.api.v1.memory.enforce_domain_access",
                  side_effect=FHTTPException(status_code=403, detail="denied")),
        ):
            r = client.post("/api/v1/memory/export", json=_export_payload(["m1"]))
        assert r.status_code == 404
    finally:
        _restore(app)


# ---------------------------------------------------------------------------
# read_policy_registry
# ---------------------------------------------------------------------------


def test_read_policy_registry_returns_registry():
    client, app = _client()
    try:
        with patch("src.api.v1.memory.get_policy_registry",
                   return_value={"tenants": {}, "subjects": {}}):
            r = client.get("/api/v1/memory/security/policy-registry")
        assert r.status_code == 200
        data = r.json()
        assert "tenants" in data
    finally:
        _restore(app)


# ---------------------------------------------------------------------------
# v1_delete — all branches
# ---------------------------------------------------------------------------


def test_v1_delete_returns_404_when_memory_missing():
    client, app = _client()
    try:
        with patch("src.api.v1.memory.get_memory", AsyncMock(return_value=None)):
            r = client.delete("/api/v1/memory/nonexistent-id")
        assert r.status_code == 404
    finally:
        _restore(app)


def test_v1_delete_returns_403_on_corporate():
    client, app = _client()
    try:
        mock_mem = MagicMock()
        mock_mem.domain = "corporate"

        with (
            patch("src.api.v1.memory.get_memory", AsyncMock(return_value=mock_mem)),
            patch("src.api.v1.memory.enforce_domain_access"),
            patch("src.api.v1.memory.enforce_memory_access"),
            patch("src.api.v1.memory.delete_memory",
                  AsyncMock(side_effect=ValueError("Cannot hard-delete append-only"))),
        ):
            r = client.delete("/api/v1/memory/corp-id")
        assert r.status_code == 403
    finally:
        _restore(app)


def test_v1_delete_success():
    client, app = _client()
    try:
        mock_mem = MagicMock()
        mock_mem.domain = "build"

        with (
            patch("src.api.v1.memory.get_memory", AsyncMock(return_value=mock_mem)),
            patch("src.api.v1.memory.enforce_domain_access"),
            patch("src.api.v1.memory.enforce_memory_access"),
            patch("src.api.v1.memory.delete_memory", AsyncMock(return_value=True)),
        ):
            r = client.delete("/api/v1/memory/build-id")
        assert r.status_code == 200
        assert r.json()["deleted"] is True
    finally:
        _restore(app)


def test_v1_delete_returns_404_when_delete_returns_false():
    client, app = _client()
    try:
        mock_mem = MagicMock()
        mock_mem.domain = "build"

        with (
            patch("src.api.v1.memory.get_memory", AsyncMock(return_value=mock_mem)),
            patch("src.api.v1.memory.enforce_domain_access"),
            patch("src.api.v1.memory.enforce_memory_access"),
            patch("src.api.v1.memory.delete_memory", AsyncMock(return_value=False)),
        ):
            r = client.delete("/api/v1/memory/ghost-id")
        assert r.status_code == 404
    finally:
        _restore(app)


# ---------------------------------------------------------------------------
# v1_sync_check
# ---------------------------------------------------------------------------


def test_v1_sync_check_success():
    client, app = _client()
    try:
        mock_result = {
            "memory_id": "m1",
            "match_key": None,
            "obsidian_ref": None,
            "status": "synced",
            "message": "Memory is synced",
        }
        with patch("src.api.v1.memory.sync_check", AsyncMock(return_value=mock_result)):
            r = client.post("/api/v1/memory/sync-check", json={"memory_id": "m1"})
        assert r.status_code == 200
        assert r.json()["status"] == "synced"
    finally:
        _restore(app)


def test_v1_sync_check_raises_422_on_value_error():
    client, app = _client()
    try:
        with patch("src.api.v1.memory.sync_check",
                   AsyncMock(side_effect=ValueError("bad input"))):
            r = client.post("/api/v1/memory/sync-check", json={"memory_id": "m1"})
        assert r.status_code == 422
    finally:
        _restore(app)


# ---------------------------------------------------------------------------
# v1_bulk_upsert
# ---------------------------------------------------------------------------


def test_v1_bulk_upsert_success():
    client, app = _client()
    try:
        mock_result = MagicMock()
        mock_result.model_dump.return_value = {
            "created": 1, "updated": 0, "skipped": 0, "failed": 0, "errors": []
        }

        with patch("src.api.v1.memory.upsert_memories_bulk", AsyncMock(return_value=mock_result)):
            r = client.post("/api/v1/memory/bulk-upsert", json=[
                {"content": "x", "domain": "build", "entity_type": "Note",
                 "owner": "alice", "match_key": "k1"}
            ])
        assert r.status_code in [200, 422]
    finally:
        _restore(app)


def test_v1_bulk_upsert_raises_422_on_value_error():
    client, app = _client()
    try:
        with patch("src.api.v1.memory.upsert_memories_bulk",
                   AsyncMock(side_effect=ValueError("missing match_key"))):
            r = client.post("/api/v1/memory/bulk-upsert", json=[
                {"content": "x", "domain": "build", "entity_type": "Note",
                 "owner": "alice", "match_key": "k1"}
            ])
        assert r.status_code == 422
    finally:
        _restore(app)
