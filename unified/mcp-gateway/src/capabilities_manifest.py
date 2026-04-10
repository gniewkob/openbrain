from __future__ import annotations

from typing import Any

from .contract_loader import load_contract

_DEFAULTS = {
    "core_tools": ["search", "get", "store", "update"],
    "advanced_tools": ["list", "get_context", "delete", "export", "sync_check"],
    "admin_tools": [
        "store_bulk",
        "upsert_bulk",
        "maintain",
        "test_data_report",
        "cleanup_build_test_data",
    ],
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


def _validate_manifest(data: Any) -> dict[str, list[str]]:
    if not isinstance(data, dict):
        raise ValueError("capabilities_manifest must be a JSON object")
    normalized: dict[str, list[str]] = {}
    for key in _DEFAULTS:
        value = data.get(key)
        if not isinstance(value, list) or not all(
            isinstance(item, str) and item.strip() for item in value
        ):
            raise ValueError(f"capabilities_manifest.{key} must be a non-empty string list")
        if len(set(value)) != len(value):
            raise ValueError(f"capabilities_manifest.{key} must not contain duplicates")
        normalized[key] = value
    return normalized


def load_capabilities_manifest() -> dict[str, list[str]]:
    data = load_contract("capabilities_manifest.json")
    return _validate_manifest(data)
