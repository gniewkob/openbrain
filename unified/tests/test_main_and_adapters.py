"""Branch coverage for src/main.py, src/http_error_adapter.py, src/response_normalizers.py."""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# src/main.py — root endpoint and prometheus_metrics endpoint
# ---------------------------------------------------------------------------


def _get_app():
    from src.main import app
    return app


def _client():
    from src.auth import require_auth
    app = _get_app()
    app.dependency_overrides[require_auth] = lambda: {"sub": "local-dev"}
    return TestClient(app, raise_server_exceptions=False), app


def test_root_endpoint_returns_service_info():
    """GET / → line 64 in main.py."""
    client, app = _client()
    try:
        r = client.get("/")
        assert r.status_code == 200
        data = r.json()
        assert data["service"] == "OpenBrain Unified"
    finally:
        app.dependency_overrides.clear()


def test_metrics_endpoint_happy_path():
    """GET /metrics with mocked gauge refresh — lines 54-56, 59."""
    client, app = _client()
    try:
        with (
            patch("src.main.refresh_memory_gauges", AsyncMock(return_value=None)),
            patch("src.main.AsyncSessionLocal") as mock_ctx,
            patch("src.main.render_prometheus_metrics", return_value="# metrics\n"),
        ):
            mock_session = AsyncMock()
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=None)
            r = client.get("/metrics")
        assert r.status_code == 200
        assert "metrics" in r.text
    finally:
        app.dependency_overrides.clear()


def test_metrics_endpoint_handles_gauge_error():
    """GET /metrics when gauge refresh raises — lines 57-58."""
    client, app = _client()
    try:
        with (
            patch("src.main.refresh_memory_gauges", AsyncMock(side_effect=RuntimeError("db down"))),
            patch("src.main.AsyncSessionLocal") as mock_ctx,
            patch("src.main.render_prometheus_metrics", return_value="# ok\n"),
        ):
            mock_session = AsyncMock()
            mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            mock_ctx.return_value.__aexit__ = AsyncMock(return_value=None)
            r = client.get("/metrics")
        # Exception is swallowed — metrics still returned
        assert r.status_code == 200
    finally:
        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# src/http_error_adapter.py — uncovered branches
# ---------------------------------------------------------------------------


def test_load_contract_falls_back_when_file_missing():
    """_load_contract except branch (lines 27-28)."""
    from src.http_error_adapter import _load_contract

    with patch("src.http_error_adapter.Path.read_text", side_effect=FileNotFoundError()):
        contract = _load_contract()

    assert "status_labels" in contract
    assert "fallback_5xx" in contract


def test_backend_error_hint_skips_non_dict_hint():
    """Hint that is not a dict → continue (line 47)."""
    from src.http_error_adapter import backend_error_message, _CONTRACT

    original_hints = _CONTRACT.get("detail_hints", {})
    try:
        _CONTRACT["detail_hints"] = {"bad": "not-a-dict"}
        msg = backend_error_message(404, "some detail")
    finally:
        _CONTRACT["detail_hints"] = original_hints

    assert "404" in msg


def test_backend_error_hint_skips_empty_needle():
    """Hint with empty 'contains' → continue (line 52)."""
    from src.http_error_adapter import backend_error_message, _CONTRACT

    original_hints = _CONTRACT.get("detail_hints", {})
    try:
        _CONTRACT["detail_hints"] = {
            "empty": {"status_code": 404, "contains": "  ", "message": "should not appear"}
        }
        msg = backend_error_message(404, "some detail")
    finally:
        _CONTRACT["detail_hints"] = original_hints

    # Fell through to the non-production default
    assert "404" in msg


# ---------------------------------------------------------------------------
# src/response_normalizers.py — line 73 (else branch)
# ---------------------------------------------------------------------------


def test_normalize_find_hits_to_scored_memories_else_branch():
    """hit without 'record'+'score' keys → out.append(hit) (line 73)."""
    from src.response_normalizers import normalize_find_hits_to_scored_memories

    hits = [{"id": "plain-hit", "score": 0.9}]  # has score but no "record"
    result = normalize_find_hits_to_scored_memories(hits)
    assert result == [{"id": "plain-hit", "score": 0.9}]
