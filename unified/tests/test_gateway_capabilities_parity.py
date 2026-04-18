from __future__ import annotations

import json
from pathlib import Path

from src import mcp_transport


def _read_manifest(repo_root: Path) -> dict[str, list[str]]:
    manifest_path = repo_root / "unified" / "contracts" / "capabilities_manifest.json"
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    return {k: v for k, v in data.items() if isinstance(v, list)}


def test_transport_uses_manifest_tool_lists() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    manifest = _read_manifest(repo_root)

    assert mcp_transport.CORE_TOOLS == manifest["core_tools"]
    assert mcp_transport.ADVANCED_TOOLS == manifest["advanced_tools"]
    assert mcp_transport.ADMIN_TOOLS == manifest["admin_tools"]
    assert mcp_transport.HTTP_OBSIDIAN_TOOLS == manifest["http_obsidian_tools"]


def test_gateway_main_loads_capabilities_from_manifest() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    gateway_main = repo_root / "unified" / "mcp-gateway" / "src" / "main.py"
    source = gateway_main.read_text(encoding="utf-8")

    assert "load_capabilities_manifest" in source
    assert "_CAPS = load_capabilities_manifest()" in source
    assert 'CORE_TOOLS = _CAPS["core_tools"]' in source
    assert 'ADVANCED_TOOLS = _CAPS["advanced_tools"]' in source
    assert 'ADMIN_TOOLS = _CAPS["admin_tools"]' in source
