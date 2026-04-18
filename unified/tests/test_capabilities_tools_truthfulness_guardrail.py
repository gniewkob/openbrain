from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


def _load_capabilities_tools_truthfulness_module():
    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "scripts" / "check_capabilities_tools_truthfulness.py"
    spec = importlib.util.spec_from_file_location(
        "check_capabilities_tools_truthfulness", script_path
    )
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_capabilities_tools_truthfulness_guardrail_passes_for_current_sources() -> None:
    module = _load_capabilities_tools_truthfulness_module()
    assert module.main() == 0


def test_capabilities_tools_truthfulness_detects_missing_tool_function() -> None:
    module = _load_capabilities_tools_truthfulness_module()
    manifest = {
        "core_tools": ["search"],
        "advanced_tools": ["list"],
        "admin_tools": ["maintain"],
        "http_obsidian_tools": ["obsidian_vaults"],
        "local_obsidian_tools": ["obsidian_vaults"],
    }
    src = """
@mcp.tool()
async def brain_search():
    return []

@mcp.tool()
async def brain_maintain():
    return {}

@mcp.tool()
async def brain_obsidian_vaults():
    return []
"""
    errors = module._check_manifest_coverage(
        src,
        manifest,
        label="x",
        obsidian_key="http_obsidian_tools",
    )
    assert any("missing tool functions" in err for err in errors)
    assert any("brain_list" in err for err in errors)


def test_capabilities_tools_truthfulness_detects_missing_mcp_tool_decorator() -> None:
    module = _load_capabilities_tools_truthfulness_module()
    manifest = {
        "core_tools": ["search"],
        "advanced_tools": [],
        "admin_tools": [],
        "http_obsidian_tools": [],
        "local_obsidian_tools": [],
    }
    src = """
async def brain_search():
    return []
"""
    errors = module._check_manifest_coverage(
        src,
        manifest,
        label="x",
        obsidian_key="http_obsidian_tools",
    )
    assert any("expected @mcp.tool decorators" in err for err in errors)
