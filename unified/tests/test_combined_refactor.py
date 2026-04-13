"""Tests for combined.app() extracted helpers."""

from __future__ import annotations
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestIsRestPath:
    def test_api_prefix_is_rest(self):
        from src.combined import _is_rest_path

        assert _is_rest_path("/api/v1/memory") is True

    def test_health_is_rest(self):
        from src.combined import _is_rest_path

        assert _is_rest_path("/health") is True

    def test_well_known_is_rest(self):
        from src.combined import _is_rest_path

        assert _is_rest_path("/.well-known/openid-configuration") is True

    def test_mcp_path_is_not_rest(self):
        from src.combined import _is_rest_path

        assert _is_rest_path("/mcp") is False

    def test_root_is_not_rest(self):
        from src.combined import _is_rest_path

        assert _is_rest_path("/") is False


class TestAuthorizeMcp:
    @pytest.mark.asyncio
    async def test_valid_internal_key_returns_true(self):
        from src.combined import _authorize_mcp

        scope = {"headers": [(b"x-internal-key", b"secret")]}
        with (
            patch("src.combined.INTERNAL_API_KEY", "secret"),
            patch("src.combined.PUBLIC_EXPOSURE", True),
        ):
            result = await _authorize_mcp(scope)
        assert result is True

    @pytest.mark.asyncio
    async def test_no_credentials_returns_false(self):
        from src.combined import _authorize_mcp

        scope = {"headers": []}
        with (
            patch("src.combined.INTERNAL_API_KEY", "secret"),
            patch("src.combined._oidc", None),
        ):
            result = await _authorize_mcp(scope)
        assert result is False
