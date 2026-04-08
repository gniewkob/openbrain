from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_DEFAULTS = {
    "find_list_query": None,
    "find_list_sort": "updated_at_desc",
    "updated_by_default": "agent",
}


def _load_request_contracts() -> dict[str, Any]:
    path = Path(__file__).resolve().parents[1] / "contracts" / "request_contracts.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return dict(_DEFAULTS)
    merged = dict(_DEFAULTS)
    merged.update({k: data.get(k, v) for k, v in _DEFAULTS.items()})
    return merged


_CONTRACTS = _load_request_contracts()


def build_list_filters(
    *,
    domain: str | None = None,
    entity_type: str | None = None,
    status: str | None = None,
    sensitivity: str | None = None,
    owner: str | None = None,
    tenant_id: str | None = None,
) -> dict[str, Any]:
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
    return filters


def build_find_list_payload(*, limit: int, filters: dict[str, Any]) -> dict[str, Any]:
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
    return {
        "memory_id": memory_id,
        "match_key": match_key,
        "obsidian_ref": obsidian_ref,
        "file_hash": file_hash,
    }


def normalize_updated_by(updated_by: str | None) -> str:
    if isinstance(updated_by, str):
        actor = updated_by.strip()
        if actor:
            return actor
    return str(_CONTRACTS["updated_by_default"])
