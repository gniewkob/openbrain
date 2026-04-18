"""Batch 3 branch coverage for remaining gaps.

Covers:
- src/request_builders.py lines 10, 15, 17: _validate_request_contracts error paths
- src/request_builders.py lines 55, 57: build_list_filters entity_type/status branches
- src/middleware.py lines 117-119: _scan_dict_values list-string item with secret
- src/middleware.py line 193: dispatch skips non-dict list item
- src/memory_reads.py lines 350-358: get_memory_domain_status_counts unknown domain
- src/memory_reads.py line 700: get_maintenance_report returns None
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock


# ---------------------------------------------------------------------------
# src/request_builders.py — _validate_request_contracts error paths
# ---------------------------------------------------------------------------


def test_validate_request_contracts_non_dict_raises():
    """Non-dict input → ValueError (line 10)."""
    from src.request_builders import _validate_request_contracts

    with pytest.raises(ValueError, match="must be a JSON object"):
        _validate_request_contracts(["not", "a", "dict"])


def test_validate_request_contracts_non_null_query_raises():
    """find_list_query not null → ValueError (line 15)."""
    from src.request_builders import _validate_request_contracts

    with pytest.raises(ValueError, match="must be null"):
        _validate_request_contracts(
            {
                "find_list_query": "SELECT *",
                "find_list_sort": "created_at desc",
                "updated_by_default": "system",
            }
        )


def test_validate_request_contracts_bad_sort_raises():
    """find_list_sort not a non-empty string → ValueError (line 17)."""
    from src.request_builders import _validate_request_contracts

    with pytest.raises(ValueError, match="must be a non-empty string"):
        _validate_request_contracts(
            {
                "find_list_query": None,
                "find_list_sort": "",
                "updated_by_default": "system",
            }
        )


# ---------------------------------------------------------------------------
# src/request_builders.py — build_list_filters entity_type/status branches
# ---------------------------------------------------------------------------


def test_build_list_filters_entity_type_branch():
    """entity_type provided → filters["entity_type"] set (line 55)."""
    from src.request_builders import build_list_filters

    result = build_list_filters(entity_type="Note")
    assert result["entity_type"] == "Note"


def test_build_list_filters_status_branch():
    """status provided → filters["status"] set (line 57)."""
    from src.request_builders import build_list_filters

    result = build_list_filters(status="active")
    assert result["status"] == "active"


# ---------------------------------------------------------------------------
# src/middleware.py — _scan_dict_values list-string secret (lines 117-119)
# ---------------------------------------------------------------------------


def test_scan_dict_values_list_string_item_with_secret_returns_true():
    """List containing a string that matches a secret pattern → (True, name)."""
    from src.middleware import _scan_dict_values

    # OpenAI API key pattern: sk- + 20+ alphanumeric chars
    data = {"items": ["sk-" + "A" * 25]}
    found, name = _scan_dict_values(data)
    assert found is True
    assert name == "openai_api_key"


# ---------------------------------------------------------------------------
# src/middleware.py line 193 — dispatch skips non-dict list items
# ---------------------------------------------------------------------------


def test_secret_scan_middleware_dispatch_skips_non_dict_list_items():
    """Payload is list with non-dict item → continue (line 193), no error."""
    import asyncio
    import os
    from src.middleware import SecretScanMiddleware
    from starlette.requests import Request
    from starlette.datastructures import Headers
    import json

    body = json.dumps([42, "plain string", None]).encode()

    async def receive():
        return {"type": "http.request", "body": body}

    async def call_next(req):
        return MagicMock(status_code=200)

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/memory/write-many",
        "headers": Headers({"content-type": "application/json"}).raw,
        "query_string": b"",
    }
    request = Request(scope, receive=receive)
    middleware = SecretScanMiddleware(app=MagicMock())

    old = os.environ.pop("DISABLE_SECRET_SCANNING", None)
    try:
        response = asyncio.run(middleware.dispatch(request, call_next))
        assert response.status_code == 200
    finally:
        if old is not None:
            os.environ["DISABLE_SECRET_SCANNING"] = old


# ---------------------------------------------------------------------------
# src/memory_reads.py lines 350-358 — unknown domain in counts
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_memory_domain_status_counts_unknown_domain():
    """Row with unknown domain → creates new key in counts dict (lines 350-358)."""
    from src.memory_reads import get_memory_domain_status_counts

    session = AsyncMock()
    mock_result = MagicMock()
    mock_result.all.return_value = [
        ("staging", "active", 5),  # unknown domain (not corporate/build/personal)
    ]
    session.execute = AsyncMock(return_value=mock_result)

    counts = await get_memory_domain_status_counts(session)

    assert "staging" in counts
    assert counts["staging"]["active"] == 5


# ---------------------------------------------------------------------------
# src/memory_reads.py line 700 — get_maintenance_report None path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_maintenance_report_returns_none_when_not_found():
    """No entry found → return None (line 700)."""
    from src.memory_reads import get_maintenance_report

    session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=mock_result)

    result = await get_maintenance_report(session, "nonexistent-id")
    assert result is None
