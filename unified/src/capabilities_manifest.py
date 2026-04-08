from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_DEFAULTS = {
    "core_tools": ["search", "get", "store", "update"],
    "advanced_tools": ["list", "get_context", "delete", "export", "sync_check"],
    "admin_tools": ["store_bulk", "upsert_bulk", "maintain"],
    "http_obsidian_tools": ["obsidian_vaults", "obsidian_read_note", "obsidian_sync"],
    "local_obsidian_tools": [
        "obsidian_vaults",
        "obsidian_read_note",
        "obsidian_sync",
        "obsidian_write_note",
        "obsidian_export",
        "obsidian_collection",
        "obsidian_bidirectional_sync",
        "obsidian_sync_status",
        "obsidian_update_note",
    ],
}


def load_capabilities_manifest() -> dict[str, list[str]]:
    manifest_path = Path(__file__).resolve().parents[1] / "contracts" / "capabilities_manifest.json"
    try:
        data: Any = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return {k: list(v) for k, v in _DEFAULTS.items()}

    normalized: dict[str, list[str]] = {}
    for key, default in _DEFAULTS.items():
        value = data.get(key)
        if isinstance(value, list) and all(isinstance(item, str) for item in value):
            normalized[key] = value
        else:
            normalized[key] = list(default)
    return normalized

