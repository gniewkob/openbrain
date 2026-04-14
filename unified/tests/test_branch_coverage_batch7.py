"""Batch 7 branch coverage for mcp_transport.py and auth.py.

Covers:
- src/mcp_transport.py line 202: X-Internal-Key header added when INTERNAL_API_KEY set
- src/mcp_transport.py lines 249-250: error response with non-JSON body
- src/mcp_transport.py line 285: readyz unexpected status code
- src/mcp_transport.py line 305: healthz fallback returns degraded
- src/mcp_transport.py line 325: api_health_fallback returns degraded
- src/auth.py lines 539-540: Redis client creation from URL
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# mcp_transport.py line 202 — X-Internal-Key header when INTERNAL_API_KEY set
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_client_adds_internal_key_header_when_set():
    """INTERNAL_API_KEY is truthy → X-Internal-Key header added to client (line 202)."""
    import src.mcp_transport as mcp_mod

    original_key = mcp_mod.INTERNAL_API_KEY
    original_client = mcp_mod._http_client
    original_config_key = mcp_mod._http_client_config_key

    try:
        mcp_mod.INTERNAL_API_KEY = "test-secret-key"
        mcp_mod._http_client = None
        mcp_mod._http_client_config_key = None

        with patch("src.mcp_transport.httpx.AsyncClient") as mock_cls:
            mock_cls.return_value = MagicMock()
            async with mcp_mod._client() as c:
                pass

        call_kwargs = mock_cls.call_args[1]
        assert "X-Internal-Key" in call_kwargs.get("headers", {})
        assert call_kwargs["headers"]["X-Internal-Key"] == "test-secret-key"
    finally:
        mcp_mod.INTERNAL_API_KEY = original_key
        mcp_mod._http_client = original_client
        mcp_mod._http_client_config_key = original_config_key


# ---------------------------------------------------------------------------
# mcp_transport.py lines 249-250 — error response with non-JSON body
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_safe_req_error_response_non_json_uses_text():
    """r.is_error + r.json() raises → detail = r.text (lines 249-250)."""
    import src.mcp_transport as mcp_mod
    import httpx

    mock_response = MagicMock(spec=httpx.Response)
    mock_response.is_error = True
    mock_response.status_code = 500
    mock_response.json.side_effect = Exception("not json")
    mock_response.text = "Internal Server Error"

    mock_client = AsyncMock()
    mock_client.request = AsyncMock(return_value=mock_response)

    with patch.object(mcp_mod, "_client") as mock_ctx_cls:
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_client)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_ctx_cls.return_value = mock_ctx

        with pytest.raises(ValueError, match="500"):
            await mcp_mod._safe_req("GET", "/api/v1/memory/test-id")


# ---------------------------------------------------------------------------
# mcp_transport.py line 285 — readyz unexpected status code
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_backend_status_readyz_unexpected_status_falls_to_healthz():
    """readyz returns non-200/503 → appends failure, tries healthz (line 285)."""
    import src.mcp_transport as mcp_mod
    import httpx

    # First call: /readyz → 404 (unexpected, appends to failures)
    # Second call: /api/v1/readyz → 404 (same)
    # Third call: /healthz → 200 (healthz fallback)
    mock_404 = MagicMock(spec=httpx.Response)
    mock_404.status_code = 404
    mock_404.json.return_value = {}

    mock_healthz_200 = MagicMock(spec=httpx.Response)
    mock_healthz_200.status_code = 200
    mock_healthz_200.json.return_value = {}

    call_count = 0

    async def make_request(method, path, **kwargs):
        nonlocal call_count
        call_count += 1
        if path == "/healthz":
            return mock_healthz_200
        return mock_404

    mock_client = AsyncMock()
    mock_client.request = make_request

    with patch.object(mcp_mod, "_client") as mock_ctx_cls:
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_client)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_ctx_cls.return_value = mock_ctx

        result = await mcp_mod._get_backend_status()

    # Lines 295-304: healthz fallback returns degraded
    assert result["probe"] == "healthz_fallback"
    assert result["status"] == "degraded"


# ---------------------------------------------------------------------------
# mcp_transport.py line 305 — healthz also fails, api_health_fallback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_backend_status_healthz_fails_falls_to_api_health():
    """readyz fails + healthz fails → api_health_fallback (lines 305, 309-325)."""
    import src.mcp_transport as mcp_mod
    import httpx

    mock_404 = MagicMock(spec=httpx.Response)
    mock_404.status_code = 404
    mock_404.json.return_value = {}

    mock_200 = MagicMock(spec=httpx.Response)
    mock_200.status_code = 200

    async def make_request(method, path, **kwargs):
        if path in ("/readyz", "/api/v1/readyz"):
            return mock_404
        if path == "/healthz":
            return mock_404  # healthz also fails (non-200)
        if path == "/api/v1/health":
            return mock_200  # api_health succeeds
        return mock_404

    mock_client = AsyncMock()
    mock_client.request = make_request

    with patch.object(mcp_mod, "_client") as mock_ctx_cls:
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_client)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_ctx_cls.return_value = mock_ctx

        result = await mcp_mod._get_backend_status()

    assert result["probe"] == "api_health_fallback"
    assert result["status"] == "degraded"


# ---------------------------------------------------------------------------
# mcp_transport.py line 325 — all probes fail → unavailable
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_backend_status_all_probes_fail_returns_unavailable():
    """All three probes raise → status='unavailable' (line 329)."""
    import src.mcp_transport as mcp_mod

    async def make_request(method, path, **kwargs):
        raise Exception("connection refused")

    mock_client = AsyncMock()
    mock_client.request = make_request

    with patch.object(mcp_mod, "_client") as mock_ctx_cls:
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_client)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_ctx_cls.return_value = mock_ctx

        result = await mcp_mod._get_backend_status()

    assert result["status"] == "unavailable"
    assert result["api"] == "unreachable"


# ---------------------------------------------------------------------------
# mcp_transport.py line 325 — api_health unexpected status → unavailable
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_backend_status_api_health_non_200_returns_unavailable():
    """readyz fails + healthz non-200 + api_health non-200 → unavailable (line 325)."""
    import src.mcp_transport as mcp_mod
    import httpx

    mock_404 = MagicMock(spec=httpx.Response)
    mock_404.status_code = 404
    mock_404.json.return_value = {}

    async def make_request(method, path, **kwargs):
        return mock_404  # all return 404 (not 200 or 200/503 dict)

    mock_client = AsyncMock()
    mock_client.request = make_request

    with patch.object(mcp_mod, "_client") as mock_ctx_cls:
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_client)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_ctx_cls.return_value = mock_ctx

        result = await mcp_mod._get_backend_status()

    # Line 325 covered, then falls through to unavailable (line 329)
    assert result["status"] == "unavailable"


# ---------------------------------------------------------------------------
# auth.py lines 539-540 — Redis client creation from URL
# ---------------------------------------------------------------------------


def test_get_redis_client_creates_client_from_url():
    """Non-memory:// REDIS_URL → creates Redis client (lines 539-540)."""
    import sys
    import src.auth as auth_mod
    import os

    original_client = auth_mod._redis_client
    auth_mod._redis_client = None

    original_url = os.environ.get("REDIS_URL")
    os.environ["REDIS_URL"] = "redis://localhost:6379/0"

    mock_client = MagicMock()
    mock_client.ping.return_value = True

    mock_redis_lib = MagicMock()
    mock_redis_lib.Redis.from_url.return_value = mock_client

    try:
        # Inject mock redis module so `import redis as _redis_lib` finds it
        with patch.dict(sys.modules, {"redis": mock_redis_lib}):
            result = auth_mod._get_redis_client()

        # Lines 539-540 executed: Redis.from_url + ping
        mock_redis_lib.Redis.from_url.assert_called_once()
        mock_client.ping.assert_called_once()
        assert result is mock_client
    finally:
        auth_mod._redis_client = original_client
        if original_url is None:
            os.environ.pop("REDIS_URL", None)
        else:
            os.environ["REDIS_URL"] = original_url
