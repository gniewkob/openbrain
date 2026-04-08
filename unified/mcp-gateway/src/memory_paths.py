from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_DEFAULT_BASE = "/api/v1/memory"
_DEFAULT_PATHS = {
    "write": "/write",
    "write_many": "/write-many",
    "find": "/find",
    "get_context": "/get-context",
    "maintain": "/maintain",
    "export": "/export",
    "sync_check": "/sync-check",
    "bulk_upsert": "/bulk-upsert",
}


def _load_contract() -> tuple[str, dict[str, str]]:
    path = Path(__file__).resolve().parents[2] / "contracts" / "memory_paths.json"
    try:
        data: Any = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return _DEFAULT_BASE, dict(_DEFAULT_PATHS)

    base = data.get("memory_base")
    if not isinstance(base, str) or not base.startswith("/"):
        base = _DEFAULT_BASE

    raw_paths = data.get("paths", {})
    paths: dict[str, str] = {}
    for key, default in _DEFAULT_PATHS.items():
        value = raw_paths.get(key)
        if isinstance(value, str) and value.startswith("/"):
            paths[key] = value
        else:
            paths[key] = default
    return base, paths


_MEMORY_BASE, _PATHS = _load_contract()


def memory_path(name: str) -> str:
    return _PATHS[name]


def memory_item_absolute_path(memory_id: str) -> str:
    return f"{_MEMORY_BASE}/{memory_id}"


def memory_absolute_path(name: str) -> str:
    return f"{_MEMORY_BASE}{memory_path(name)}"

