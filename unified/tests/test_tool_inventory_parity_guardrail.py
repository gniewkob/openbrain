from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


def _load_tool_inventory_parity_module():
    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "scripts" / "check_tool_inventory_parity.py"
    spec = importlib.util.spec_from_file_location(
        "check_tool_inventory_parity", script_path
    )
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_tool_inventory_parity_guardrail_passes_for_current_sources() -> None:
    module = _load_tool_inventory_parity_module()
    assert module.main() == 0


def test_tool_inventory_parity_detects_non_obsidian_drift() -> None:
    module = _load_tool_inventory_parity_module()
    http_src = """
@mcp.tool()
async def brain_store():
    return {}

@mcp.tool()
async def brain_debug_only():
    return {}
"""
    gateway_src = """
@mcp.tool()
async def brain_store():
    return {}
"""
    errors = module._check_tool_inventory_parity(http_src, gateway_src)
    assert any("non-obsidian tool inventory drift" in err for err in errors)


def test_tool_inventory_parity_detects_http_obsidian_subset_drift() -> None:
    module = _load_tool_inventory_parity_module()
    http_src = """
@mcp.tool()
async def brain_store():
    return {}

@mcp.tool()
async def brain_obsidian_sync_status():
    return {}
"""
    gateway_src = """
@mcp.tool()
async def brain_store():
    return {}

@mcp.tool()
async def brain_obsidian_sync():
    return {}
"""
    errors = module._check_tool_inventory_parity(http_src, gateway_src)
    assert any("HTTP transport obsidian tool set drifted" in err for err in errors)
