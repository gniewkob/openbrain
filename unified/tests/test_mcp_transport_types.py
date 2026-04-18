"""Tests for mcp_transport return type contracts."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_safe_req_returns_list_from_find_endpoint():
    """_safe_req must transparently return list responses from find/export endpoints."""
    from src.mcp_transport import _safe_req

    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_response.is_error = False
    mock_response.json = lambda: [{"record": {"id": "1"}, "score": 0.9}]

    with patch("src.mcp_transport._client") as mock_client_ctx:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.request = AsyncMock(return_value=mock_response)
        mock_client_ctx.return_value = mock_client

        result = await _safe_req("POST", "/api/v1/memory/find", json={"query": "test"})

    assert isinstance(result, list)
    assert result[0]["score"] == 0.9


@pytest.mark.asyncio
async def test_safe_req_returns_dict_from_store_endpoint():
    """_safe_req must return dict responses from store/write endpoints."""
    from src.mcp_transport import _safe_req

    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_response.is_error = False
    mock_response.json = lambda: {"status": "stored", "id": "abc-123"}

    with patch("src.mcp_transport._client") as mock_client_ctx:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.request = AsyncMock(return_value=mock_response)
        mock_client_ctx.return_value = mock_client

        result = await _safe_req("POST", "/api/v1/memory/write", json={"content": "x"})

    assert isinstance(result, dict)
    assert result["status"] == "stored"
