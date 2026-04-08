from __future__ import annotations

from typing import Any


def _api_component(api: str) -> str:
    if api == "reachable":
        return "healthy"
    if api == "unreachable":
        return "unavailable"
    return "unknown"


def _store_component(state: str) -> str:
    if state == "ok":
        return "healthy"
    if state == "degraded":
        return "degraded"
    if state == "unavailable":
        return "unavailable"
    return "unknown"


def build_capabilities_health(
    backend: dict[str, Any], obsidian_status: str
) -> dict[str, Any]:
    api = _api_component(str(backend.get("api", "unknown")))
    db = _store_component(str(backend.get("db", "unknown")))
    vector_store = _store_component(str(backend.get("vector_store", "unknown")))
    if api == "unavailable":
        overall = "unavailable"
    elif backend.get("status") == "unavailable":
        overall = "unavailable"
    elif backend.get("status") == "degraded":
        overall = "degraded"
    elif any(x in {"degraded", "unknown", "unavailable"} for x in (db, vector_store)):
        overall = "degraded"
    else:
        overall = "healthy"
    return {
        "overall": overall,
        "source": backend.get("probe", "unknown"),
        "components": {
            "api": api,
            "db": db,
            "vector_store": vector_store,
            "obsidian": "enabled" if obsidian_status == "enabled" else "disabled",
        },
    }
