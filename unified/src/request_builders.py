from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _validate_request_contracts(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError("request_contracts must be a JSON object")
    query = data.get("find_list_query")
    sort = data.get("find_list_sort")
    updated_by_default = data.get("updated_by_default")
    if query is not None:
        raise ValueError("request_contracts.find_list_query must be null")
    if not isinstance(sort, str) or not sort.strip():
        raise ValueError("request_contracts.find_list_sort must be a non-empty string")
    if not isinstance(updated_by_default, str) or not updated_by_default.strip():
        raise ValueError(
            "request_contracts.updated_by_default must be a non-empty string"
        )
    normalized_sort = sort.strip()
    normalized_updated_by_default = updated_by_default.strip()
    return {
        "find_list_query": None,
        "find_list_sort": normalized_sort,
        "updated_by_default": normalized_updated_by_default,
    }


def _load_request_contracts() -> dict[str, Any]:
    path = Path(__file__).resolve().parents[1] / "contracts" / "request_contracts.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return _validate_request_contracts(data)


_CONTRACTS = _load_request_contracts()


def build_list_filters(
    *,
    domain: str | None = None,
    entity_type: str | None = None,
    status: str | None = None,
    sensitivity: str | None = None,
    owner: str | None = None,
    tenant_id: str | None = None,
    include_test_data: bool | None = None,
) -> dict[str, Any]:
    """Build a filters dict from non-None keyword arguments for list queries."""
    filters: dict[str, Any] = {}
    if domain:
        filters["domain"] = domain
    if entity_type:
        filters["entity_type"] = entity_type
    if status:
        filters["status"] = status
    if sensitivity:
        filters["sensitivity"] = sensitivity
    if owner:
        filters["owner"] = owner
    if tenant_id:
        filters["tenant_id"] = tenant_id
    if include_test_data is True:
        filters["include_test_data"] = True
    return filters


def build_find_list_payload(*, limit: int, filters: dict[str, Any]) -> dict[str, Any]:
    """Build the POST /find/list request body using contract-defined sort and query."""
    return {
        "query": _CONTRACTS["find_list_query"],
        "filters": filters,
        "limit": limit,
        "sort": _CONTRACTS["find_list_sort"],
    }


def build_find_search_payload(
    *,
    query: str,
    limit: int,
    filters: dict[str, Any],
) -> dict[str, Any]:
    """Build the POST /find/search request body for semantic search."""
    return {
        "query": query,
        "filters": filters,
        "limit": limit,
    }


def build_sync_check_payload(
    *,
    memory_id: str | None = None,
    match_key: str | None = None,
    obsidian_ref: str | None = None,
    file_hash: str | None = None,
) -> dict[str, Any]:
    """Build the sync-check request body from optional lookup fields."""
    return {
        "memory_id": memory_id,
        "match_key": match_key,
        "obsidian_ref": obsidian_ref,
        "file_hash": file_hash,
    }


def normalize_updated_by(updated_by: str | None) -> str:
    """Return a non-empty actor string, falling back to the contract default."""
    if isinstance(updated_by, str):
        actor = updated_by.strip()
        if actor:
            return actor
    return str(_CONTRACTS["updated_by_default"])


def canonical_updated_by() -> str:
    """Compatibility placeholder for patch payloads.

    API v1 enforces authenticated subject as authoritative audit actor.
    """
    return str(_CONTRACTS["updated_by_default"])
