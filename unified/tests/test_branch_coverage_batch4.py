"""Batch 4 branch coverage for remaining small gaps.

Covers:
- src/health.py lines 37-38: _check_vector_store exception → "degraded"
- src/health.py line 69: readyz DB failure → 503 JSONResponse
- src/exceptions.py lines 282-283: http_exception_handler dict detail with "code"
- src/capabilities_manifest.py line 34: _validate_manifest non-dict input
- src/config.py lines 289, 294, 304, 309: backwards compat utility functions
- src/app_factory.py line 39: HSTS header in public_mode
- src/app_factory.py lines 93-98: CORS origins in public_mode
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# src/api/v1/health.py lines 37-38 — _check_vector_store exception
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_vector_store_exception_returns_degraded():
    """httpx.AsyncClient.post raises → returns 'degraded' (lines 37-38)."""
    from src.api.v1.health import _check_vector_store

    with patch("src.api.v1.health.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=Exception("connection refused"))
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)
        result = await _check_vector_store()

    assert result == "degraded"


# ---------------------------------------------------------------------------
# src/api/v1/health.py line 69 — readyz DB failure → 503
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_readyz_db_failure_returns_503():
    """DB execute raises → db_status='degraded', 503 JSONResponse (line 69)."""
    from src.api.v1.health import readyz
    from fastapi.responses import JSONResponse

    with (
        patch("src.api.v1.health.AsyncSessionLocal") as mock_ctx,
        patch("src.api.v1.health._check_vector_store", AsyncMock(return_value="ok")),
    ):
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(side_effect=Exception("db down"))
        mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.return_value.__aexit__ = AsyncMock(return_value=None)
        result = await readyz()

    assert isinstance(result, JSONResponse)
    assert result.status_code == 503


# ---------------------------------------------------------------------------
# src/api/v1/health.py line 69 — readyz success path → returns dict
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_readyz_success_returns_dict():
    """DB OK + vector store OK → returns payload dict (line 69)."""
    from src.api.v1.health import readyz

    with (
        patch("src.api.v1.health.AsyncSessionLocal") as mock_ctx,
        patch("src.api.v1.health._check_vector_store", AsyncMock(return_value="ok")),
    ):
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=None)
        mock_ctx.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_ctx.return_value.__aexit__ = AsyncMock(return_value=None)
        result = await readyz()

    assert isinstance(result, dict)
    assert result["status"] == "ok"


# ---------------------------------------------------------------------------
# src/exceptions.py lines 282-283 — http_exception_handler dict detail with "code"
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_http_exception_handler_dict_detail_with_code():
    """detail is dict with 'code' key → uses code from detail (lines 282-283)."""
    import json
    from fastapi import HTTPException
    from src.exceptions import http_exception_handler

    mock_request = MagicMock()
    exc = HTTPException(
        status_code=422,
        detail={"code": "custom_error", "message": "custom message"},
    )
    response = await http_exception_handler(mock_request, exc)
    body = json.loads(response.body)
    assert body["error"]["code"] == "custom_error"
    assert body["error"]["message"] == "custom message"


# ---------------------------------------------------------------------------
# src/capabilities_manifest.py line 34 — _validate_manifest non-dict input
# ---------------------------------------------------------------------------


def test_validate_manifest_non_dict_raises():
    """Non-dict input → ValueError (line 34)."""
    from src.capabilities_manifest import _validate_manifest

    with pytest.raises(ValueError, match="must be a JSON object"):
        _validate_manifest(["not", "a", "dict"])


# ---------------------------------------------------------------------------
# src/config.py lines 289, 294, 304, 309 — backwards compat utility functions
# ---------------------------------------------------------------------------


def test_get_database_url_returns_string():
    """get_database_url() → returns DB URL string (line 289)."""
    from src.config import get_database_url

    result = get_database_url()
    assert isinstance(result, str)


def test_is_public_mode_returns_bool():
    """is_public_mode() → returns bool (line 294)."""
    from src.config import is_public_mode

    result = is_public_mode()
    assert isinstance(result, bool)


def test_get_public_base_url_returns_string():
    """get_public_base_url() → returns string (line 304)."""
    from src.config import get_public_base_url

    result = get_public_base_url()
    assert isinstance(result, str)


def test_get_oidc_issuer_url_returns_string():
    """get_oidc_issuer_url() → returns string (line 309)."""
    from src.config import get_oidc_issuer_url

    result = get_oidc_issuer_url()
    assert isinstance(result, str)


# ---------------------------------------------------------------------------
# src/app_factory.py line 39 — HSTS header in public_mode
# ---------------------------------------------------------------------------


def test_security_headers_middleware_adds_hsts_in_public_mode():
    """public_mode=True → Strict-Transport-Security header added (line 39)."""
    import asyncio
    from src.app_factory import SecurityHeadersMiddleware

    middleware = SecurityHeadersMiddleware(app=MagicMock())

    response_mock = MagicMock()
    response_mock.headers = {}

    async def call_next(req):
        return response_mock

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/test",
        "headers": [],
        "query_string": b"",
    }
    from starlette.requests import Request

    request = Request(scope)

    with patch("src.app_factory.get_config") as mock_cfg:
        mock_cfg.return_value.auth.public_mode = True
        result = asyncio.run(middleware.dispatch(request, call_next))

    assert "Strict-Transport-Security" in result.headers


# ---------------------------------------------------------------------------
# src/app_factory.py lines 93-98 — CORS origins in public_mode with fallback
# ---------------------------------------------------------------------------


def test_create_app_public_mode_no_custom_origins_uses_public_base_url():
    """public_mode=True, default localhost origins → use public_base_url (lines 93-98)."""
    from unittest.mock import MagicMock, patch

    mock_lifespan = MagicMock()

    with patch("src.app_factory.get_config") as mock_cfg:
        cfg = MagicMock()
        cfg.auth.public_mode = True
        cfg.auth.public_base_url = "https://example.com"
        cfg.auth.oidc_issuer_url = "https://auth.example.com"
        cfg.auth.internal_api_key = "x" * 32
        cfg.cors.get_origins_list.return_value = [
            "http://localhost:*",
            "http://127.0.0.1:*",
        ]
        cfg.rate_limit_per_minute = 60
        cfg.redis.url = "memory://"
        mock_cfg.return_value = cfg

        from src.app_factory import create_app

        app = create_app(public_base_url="https://example.com", lifespan=mock_lifespan)

    assert app is not None
