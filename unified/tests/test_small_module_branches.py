"""Targeted branch coverage for small utility modules.

Covers uncovered branches in:
- src/capabilities_health.py
- src/capabilities_metadata.py
- src/memory_paths.py
- src/runtime_limits.py
"""

from __future__ import annotations

import json
import pytest
from unittest.mock import patch


# ---------------------------------------------------------------------------
# capabilities_health — _api_component and _store_component "unknown" branches
# ---------------------------------------------------------------------------


def test_api_component_unknown_returns_unknown():
    from src.capabilities_health import _api_component

    assert _api_component("something-else") == "unknown"


def test_store_component_unavailable_returns_unavailable():
    from src.capabilities_health import _store_component

    assert _store_component("unavailable") == "unavailable"


def test_build_capabilities_health_status_unavailable():
    """backend['status'] == 'unavailable' branch (line 33)."""
    from src.capabilities_health import build_capabilities_health

    result = build_capabilities_health(
        backend={"api": "reachable", "status": "unavailable"},
        obsidian_status="disabled",
    )
    assert result["overall"] == "unavailable"


def test_build_capabilities_health_status_degraded():
    """backend['status'] == 'degraded' branch (line 35)."""
    from src.capabilities_health import build_capabilities_health

    result = build_capabilities_health(
        backend={"api": "reachable", "status": "degraded"},
        obsidian_status="disabled",
    )
    assert result["overall"] == "degraded"


def test_build_capabilities_health_degraded_component():
    """any(x in {degraded, ...}) branch (line 36-37)."""
    from src.capabilities_health import build_capabilities_health

    result = build_capabilities_health(
        backend={"api": "reachable", "db": "unknown", "status": "ok"},
        obsidian_status="disabled",
    )
    assert result["overall"] == "degraded"


# ---------------------------------------------------------------------------
# capabilities_metadata — validation error branches
# ---------------------------------------------------------------------------


def test_validate_metadata_raises_when_changelog_not_dict():
    from src.capabilities_metadata import _validate_metadata

    with pytest.raises(ValueError, match="must be an object"):
        _validate_metadata({"api_version": "1.0.0", "schema_changelog": ["not", "a", "dict"]})


def test_validate_metadata_raises_when_changelog_key_not_semver():
    from src.capabilities_metadata import _validate_metadata

    with pytest.raises(ValueError, match="keys must match"):
        _validate_metadata(
            {"api_version": "1.0.0", "schema_changelog": {"bad-key": "description"}}
        )


def test_validate_metadata_raises_when_changelog_value_empty():
    from src.capabilities_metadata import _validate_metadata

    with pytest.raises(ValueError, match="values must be non-empty"):
        _validate_metadata(
            {"api_version": "1.0.0", "schema_changelog": {"1.0.0": "   "}}
        )


# ---------------------------------------------------------------------------
# memory_paths — _load_contract fallback branches
# ---------------------------------------------------------------------------


def test_load_contract_falls_back_to_defaults_on_read_error(tmp_path):
    """json.loads fails → returns _DEFAULT_BASE + default paths (lines 26-27)."""
    from src import memory_paths

    with patch.object(
        memory_paths.Path,
        "read_text",
        side_effect=FileNotFoundError("no file"),
    ):
        base, paths = memory_paths._load_contract()

    assert base == "/api/v1/memory"
    assert "find" in paths


def test_load_contract_uses_default_base_when_invalid(tmp_path):
    """base not str or not starting with '/' → falls back (line 31)."""
    from src import memory_paths

    bad_data = json.dumps({"memory_base": "no-leading-slash", "paths": {}})
    with patch.object(memory_paths.Path, "read_text", return_value=bad_data):
        base, paths = memory_paths._load_contract()

    assert base == "/api/v1/memory"


def test_load_contract_uses_default_path_when_value_invalid(tmp_path):
    """path value not str or not starting with '/' → uses default (line 40)."""
    from src import memory_paths

    bad_data = json.dumps({"memory_base": "/api/v1/memory", "paths": {"find": "no-slash"}})
    with patch.object(memory_paths.Path, "read_text", return_value=bad_data):
        _, paths = memory_paths._load_contract()

    assert paths["find"] == "/find"  # falls back to _DEFAULT_PATHS["find"]


# ---------------------------------------------------------------------------
# runtime_limits — validation error branches
# ---------------------------------------------------------------------------


def test_validate_runtime_limits_raises_when_not_dict():
    from src.runtime_limits import _validate_runtime_limits

    with pytest.raises(ValueError, match="must be a JSON object"):
        _validate_runtime_limits(["not", "a", "dict"])


def test_validate_runtime_limits_raises_when_value_not_int():
    from src.runtime_limits import _validate_runtime_limits

    with pytest.raises(ValueError, match="must be an integer"):
        _validate_runtime_limits(
            {
                "max_search_top_k": "not-an-int",
                "max_list_limit": 200,
                "max_sync_limit": 200,
                "max_bulk_items": 100,
            }
        )
