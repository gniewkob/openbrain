from __future__ import annotations

import json
from pathlib import Path
import sys
from unittest.mock import AsyncMock, patch

import pytest

from src import mcp_transport

ROOT = Path(__file__).resolve().parents[1]
GATEWAY_TESTS = ROOT / "mcp-gateway" / "tests"
if str(GATEWAY_TESTS) not in sys.path:
    sys.path.insert(0, str(GATEWAY_TESTS))

from helpers import load_gateway_main  # noqa: E402

try:
    _gateway = load_gateway_main()
    _GATEWAY_IMPORT_ERROR = None
except Exception as exc:  # pragma: no cover - import environment dependent
    _gateway = None
    _GATEWAY_IMPORT_ERROR = exc


def _contract() -> dict:
    path = (
        Path(__file__).resolve().parents[1]
        / "contracts"
        / "capabilities_response_contract.json"
    )
    return json.loads(path.read_text(encoding="utf-8"))


def _cap_metadata() -> dict:
    path = (
        Path(__file__).resolve().parents[1]
        / "contracts"
        / "capabilities_metadata.json"
    )
    return json.loads(path.read_text(encoding="utf-8"))


def _cap_manifest() -> dict:
    path = (
        Path(__file__).resolve().parents[1]
        / "contracts"
        / "capabilities_manifest.json"
    )
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.asyncio
async def test_http_transport_capabilities_follow_response_contract() -> None:
    contract = _contract()
    metadata = _cap_metadata()
    manifest = _cap_manifest()
    backend = {
        "status": "ok",
        "api": "reachable",
        "db": "ok",
        "vector_store": "ok",
        "probe": "readyz",
    }
    with (
        patch.object(mcp_transport, "_get_backend_status", AsyncMock(return_value=backend)),
        patch.object(mcp_transport, "ENABLE_HTTP_OBSIDIAN_TOOLS", False),
    ):
        caps = await mcp_transport.brain_capabilities()

    for key in contract["required_top_level_keys"]:
        assert key in caps
    assert caps["api_version"] == metadata["api_version"]
    assert caps["schema_changelog"] == metadata["schema_changelog"]
    for key in contract["backend_required_keys"]:
        assert key in caps["backend"]
    for key in contract["health_required_keys"]:
        assert key in caps["health"]
    for key in contract["health_component_required_keys"]:
        assert key in caps["health"]["components"]
    for key in contract["obsidian_required_keys"]:
        assert key in caps["obsidian"]

    assert caps["health"]["overall"] in contract["health_overall_values"]
    assert caps["obsidian"]["mode"] in contract["obsidian_modes"]
    assert caps["obsidian"]["status"] in contract["obsidian_statuses"]
    assert isinstance(caps["obsidian"]["tools"], list)
    assert caps["tier_1_core"]["tools"] == manifest["core_tools"]
    assert caps["tier_2_advanced"]["tools"] == manifest["advanced_tools"]
    assert caps["tier_3_admin"]["tools"] == manifest["admin_tools"]
    assert "test_data_report" in caps["tier_3_admin"]["tools"]
    assert "cleanup_build_test_data" in caps["tier_3_admin"]["tools"]


@pytest.mark.asyncio
async def test_gateway_capabilities_follow_response_contract_when_available() -> None:
    if _GATEWAY_IMPORT_ERROR is not None:
        pytest.skip(f"gateway import failed: {_GATEWAY_IMPORT_ERROR}")
    contract = _contract()
    metadata = _cap_metadata()
    manifest = _cap_manifest()
    backend = {
        "status": "ok",
        "api": "reachable",
        "db": "ok",
        "vector_store": "ok",
        "probe": "readyz",
    }
    with patch("_gateway_src.main._get_backend_status", AsyncMock(return_value=backend)):
        caps = await _gateway.brain_capabilities()

    for key in contract["required_top_level_keys"]:
        assert key in caps
    assert caps["api_version"] == metadata["api_version"]
    assert caps["schema_changelog"] == metadata["schema_changelog"]
    for key in contract["backend_required_keys"]:
        assert key in caps["backend"]
    for key in contract["health_required_keys"]:
        assert key in caps["health"]
    for key in contract["health_component_required_keys"]:
        assert key in caps["health"]["components"]
    for key in contract["obsidian_required_keys"]:
        assert key in caps["obsidian"]

    assert caps["health"]["overall"] in contract["health_overall_values"]
    assert caps["obsidian"]["mode"] in contract["obsidian_modes"]
    assert caps["obsidian"]["status"] in contract["obsidian_statuses"]
    assert isinstance(caps["obsidian"]["tools"], list)
    assert caps["tier_1_core"]["tools"] == manifest["core_tools"]
    assert caps["tier_2_advanced"]["tools"] == manifest["advanced_tools"]
    assert caps["tier_3_admin"]["tools"] == manifest["admin_tools"]
    assert "test_data_report" in caps["tier_3_admin"]["tools"]
    assert "cleanup_build_test_data" in caps["tier_3_admin"]["tools"]
