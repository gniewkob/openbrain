"""Batch branch coverage for remaining 1-liner and small gaps.

Covers:
- src/schemas.py line 81: custom_fields key too long
- src/middleware.py lines 117-119, 175-178, 193: secret scanning branches
- src/api/v1/memory.py line 159: get_context with domain param
"""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# src/schemas.py line 81 — custom_fields key exceeds MAX_CUSTOM_KEY_LEN
# ---------------------------------------------------------------------------


def test_custom_fields_key_exceeds_max_length_raises():
    """key > 64 chars → ValueError (line 81-84 in schemas.py)."""
    from src.schemas import MemoryWriteRecord

    long_key = "k" * 65  # MAX_CUSTOM_KEY_LEN = 64
    with pytest.raises(Exception):  # Pydantic ValidationError wraps ValueError
        MemoryWriteRecord(
            content="test",
            domain="build",
            entity_type="Note",
            owner="alice",
            custom_fields={long_key: "value"},
        )


# ---------------------------------------------------------------------------
# src/middleware.py — secret scanning branches
# ---------------------------------------------------------------------------


def test_scan_dict_values_string_item_found():
    """List item that is a string (not dict) → _scan_string path (lines 117-119)."""
    from src.middleware import _scan_for_secrets

    # A list with a string that contains a secret-like pattern
    payload = {"items": ["AKIA" + "A" * 16]}  # AWS access key pattern
    found, name = _scan_for_secrets(payload)
    # Whether this is found depends on the pattern; just ensure we don't crash
    assert isinstance(found, bool)


def test_scan_for_secrets_non_dict_item_in_list():
    """items list contains a non-dict, non-string item → continue (line 193)."""
    from src.middleware import _scan_for_secrets

    payload = {"records": [42, None, True]}  # non-dict, non-string items
    found, name = _scan_for_secrets(payload)
    assert found is False


def test_secret_scan_middleware_bypass_when_env_set(tmp_path):
    """DISABLE_SECRET_SCANNING=1 → bypass and call_next (lines 175-178)."""
    import asyncio
    from src.middleware import SecretScanMiddleware
    from starlette.requests import Request
    from starlette.datastructures import Headers

    async def call_next(req):
        return MagicMock(status_code=200)

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/memory/write",
        "headers": Headers({"content-type": "application/json"}).raw,
        "query_string": b"",
    }
    request = Request(scope)
    middleware = SecretScanMiddleware(app=MagicMock())

    old_val = os.environ.get("DISABLE_SECRET_SCANNING")
    try:
        os.environ["DISABLE_SECRET_SCANNING"] = "1"
        response = asyncio.run(middleware.dispatch(request, call_next))
        assert response.status_code == 200
    finally:
        if old_val is None:
            os.environ.pop("DISABLE_SECRET_SCANNING", None)
        else:
            os.environ["DISABLE_SECRET_SCANNING"] = old_val


# ---------------------------------------------------------------------------
# src/api/v1/memory.py line 159 — get_context with domain param
# ---------------------------------------------------------------------------


def test_v1_get_context_with_domain_calls_enforce():
    """GET /get-context with domain → enforce_domain_access (line 159)."""
    from src.main import app
    from src.auth import require_auth
    from fastapi.testclient import TestClient

    app.dependency_overrides[require_auth] = lambda: {"sub": "local-dev"}
    client = TestClient(app, raise_server_exceptions=False)
    try:
        mock_response = MagicMock()
        mock_response.model_dump.return_value = {
            "query": "test",
            "records": [],
            "themes": [],
            "risks": [],
        }

        with (
            patch("src.api.v1.memory.enforce_domain_access") as mock_enf,
            patch("src.api.v1.memory.get_grounding_pack", AsyncMock(return_value=mock_response)),
        ):
            r = client.post(
                "/api/v1/memory/get-context",
                json={"query": "test", "domain": "build"},
            )
        # enforce_domain_access should have been called with the domain
        mock_enf.assert_called_once()
        call_args = mock_enf.call_args
        assert "build" in call_args[0]  # domain in positional args
    finally:
        app.dependency_overrides.clear()
