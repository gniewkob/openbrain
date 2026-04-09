from __future__ import annotations

import asyncio
import json
from pathlib import Path
import re
from unittest.mock import AsyncMock, patch

from src.capabilities_manifest import _validate_manifest, load_capabilities_manifest
from src.capabilities_metadata import _validate_metadata, load_capabilities_metadata
from src.http_error_adapter import backend_error_message
from src.memory_paths import memory_absolute_path
from src.request_builders import (
    _validate_request_contracts,
    build_find_list_payload,
    normalize_updated_by,
)
from src.runtime_limits import _validate_runtime_limits, load_runtime_limits
from src import mcp_transport


def _contracts_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "contracts"


def test_all_contract_files_are_valid_json() -> None:
    for path in _contracts_dir().glob("*.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        assert isinstance(data, dict), f"{path.name} must contain JSON object"


def test_capabilities_contract_is_loaded_by_adapter() -> None:
    manifest = load_capabilities_manifest()
    raw = json.loads(
        (_contracts_dir() / "capabilities_manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["core_tools"] == raw["core_tools"]
    assert manifest["advanced_tools"] == raw["advanced_tools"]
    assert manifest["admin_tools"] == raw["admin_tools"]


def test_capabilities_manifest_validation_rejects_duplicates() -> None:
    bad = {
        "core_tools": ["search", "search"],
        "advanced_tools": ["list"],
        "admin_tools": ["maintain"],
        "http_obsidian_tools": ["obsidian_vaults"],
        "local_obsidian_tools": ["obsidian_vaults"],
    }
    try:
        _validate_manifest(bad)
        assert False, "expected ValueError for duplicate capability names"
    except ValueError as exc:
        assert "duplicates" in str(exc)


def test_capabilities_manifest_validation_requires_string_lists() -> None:
    bad = {
        "core_tools": ["search", ""],
        "advanced_tools": ["list"],
        "admin_tools": ["maintain"],
        "http_obsidian_tools": ["obsidian_vaults"],
        "local_obsidian_tools": ["obsidian_vaults"],
    }
    try:
        _validate_manifest(bad)
        assert False, "expected ValueError for blank capability names"
    except ValueError as exc:
        assert "non-empty string list" in str(exc)


def test_capabilities_metadata_contract_is_loaded_by_adapter() -> None:
    metadata = load_capabilities_metadata()
    raw = json.loads(
        (_contracts_dir() / "capabilities_metadata.json").read_text(encoding="utf-8")
    )
    assert metadata["api_version"] == raw["api_version"]
    assert metadata["schema_changelog"] == raw["schema_changelog"]
    assert re.fullmatch(r"\d+\.\d+\.\d+", metadata["api_version"])
    assert metadata["api_version"] in metadata["schema_changelog"]


def test_capabilities_metadata_validation_rejects_malformed_version() -> None:
    bad = {"api_version": "v2", "schema_changelog": {"2.3.0": "ok"}}
    try:
        _validate_metadata(bad)
        assert False, "expected ValueError for malformed api_version"
    except ValueError as exc:
        assert "api_version" in str(exc)


def test_capabilities_metadata_validation_requires_current_changelog_entry() -> None:
    bad = {"api_version": "2.3.0", "schema_changelog": {"2.2.0": "old"}}
    try:
        _validate_metadata(bad)
        assert False, "expected ValueError when api_version entry is missing"
    except ValueError as exc:
        assert "api_version entry" in str(exc)


def test_request_contract_defaults_are_applied() -> None:
    payload = build_find_list_payload(limit=3, filters={})
    assert payload["query"] is None
    assert payload["sort"] == "updated_at_desc"
    assert normalize_updated_by("  ") == "agent"


def test_request_contract_validation_rejects_invalid_updated_by_default() -> None:
    bad = {
        "find_list_query": None,
        "find_list_sort": "updated_at_desc",
        "updated_by_default": "   ",
    }
    try:
        _validate_request_contracts(bad)
        assert False, "expected ValueError for blank updated_by_default"
    except ValueError as exc:
        assert "updated_by_default" in str(exc)


def test_request_contract_validation_trims_string_fields() -> None:
    raw = {
        "find_list_query": None,
        "find_list_sort": "  updated_at_desc  ",
        "updated_by_default": "  agent  ",
    }
    normalized = _validate_request_contracts(raw)
    assert normalized["find_list_sort"] == "updated_at_desc"
    assert normalized["updated_by_default"] == "agent"


def test_runtime_limits_contract_is_loaded() -> None:
    limits = load_runtime_limits()
    raw = json.loads(
        (_contracts_dir() / "runtime_limits.json").read_text(encoding="utf-8")
    )
    assert limits["max_search_top_k"] == raw["max_search_top_k"]
    assert limits["max_list_limit"] == raw["max_list_limit"]
    assert limits["max_sync_limit"] == raw["max_sync_limit"]
    assert limits["max_bulk_items"] == raw["max_bulk_items"]


def test_runtime_limits_validation_rejects_non_positive_values() -> None:
    bad = {
        "max_search_top_k": 100,
        "max_list_limit": 0,
        "max_sync_limit": 200,
        "max_bulk_items": 100,
    }
    try:
        _validate_runtime_limits(bad)
        assert False, "expected ValueError for non-positive runtime limit"
    except ValueError as exc:
        assert "max_list_limit" in str(exc)


def test_memory_paths_contract_is_loaded() -> None:
    raw = json.loads((_contracts_dir() / "memory_paths.json").read_text(encoding="utf-8"))
    assert memory_absolute_path("find") == f'{raw["memory_base"]}{raw["paths"]["find"]}'
    assert memory_absolute_path("write") == f'{raw["memory_base"]}{raw["paths"]["write"]}'


def test_http_error_contract_prod_mode_masks_detail(monkeypatch) -> None:
    monkeypatch.setenv("ENV", "production")
    msg = backend_error_message(500, {"detail": "secret"})
    assert "500" in msg
    assert "secret" not in msg


def test_capabilities_tools_map_to_real_http_transport_functions() -> None:
    manifest = load_capabilities_manifest()
    expected = {"capabilities"}
    expected.update(manifest["core_tools"])
    expected.update(manifest["advanced_tools"])
    expected.update(manifest["admin_tools"])

    for tool in sorted(expected):
        fn = getattr(mcp_transport, f"brain_{tool}", None)
        assert callable(fn), f"brain_{tool} must be implemented by HTTP MCP transport"

    if mcp_transport.ENABLE_HTTP_OBSIDIAN_TOOLS:
        for tool in manifest["http_obsidian_tools"]:
            fn = getattr(mcp_transport, f"brain_{tool}", None)
            assert callable(fn), (
                f"brain_{tool} must exist when ENABLE_HTTP_OBSIDIAN_TOOLS=true"
            )


def test_http_obsidian_capabilities_follow_runtime_registration_state() -> None:
    manifest = load_capabilities_manifest()
    expected_enabled = (
        mcp_transport.ENABLE_HTTP_OBSIDIAN_TOOLS
        and mcp_transport._http_obsidian_tools_registered()
    )
    backend = {
        "status": "ok",
        "api": "reachable",
        "db": "ok",
        "vector_store": "ok",
        "probe": "readyz",
    }
    with patch.object(
        mcp_transport, "_get_backend_status", AsyncMock(return_value=backend)
    ):
        caps = asyncio.run(mcp_transport.brain_capabilities())

    if expected_enabled:
        assert caps["obsidian_http"]["status"] == "enabled"
        assert caps["obsidian_http"]["tools"] == manifest["http_obsidian_tools"]
    else:
        assert caps["obsidian_http"]["status"] == "disabled"
        assert caps["obsidian_http"]["tools"] == []
