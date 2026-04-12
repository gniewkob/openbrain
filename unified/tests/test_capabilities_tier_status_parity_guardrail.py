from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


def _load_capabilities_tier_status_parity_module():
    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "scripts" / "check_capabilities_tier_status_parity.py"
    spec = importlib.util.spec_from_file_location(
        "check_capabilities_tier_status_parity", script_path
    )
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_capabilities_tier_status_parity_guardrail_passes_for_current_sources() -> None:
    module = _load_capabilities_tier_status_parity_module()
    assert module.main() == 0


def test_capabilities_tier_status_parity_detects_value_drift() -> None:
    module = _load_capabilities_tier_status_parity_module()
    transport_src = """
async def brain_capabilities():
    return {
        "tier_1_core": {"status": "stable", "tools": []},
        "tier_2_advanced": {"status": "active", "tools": []},
        "tier_3_admin": {"status": "guarded", "tools": []},
    }
"""
    gateway_src = """
async def brain_capabilities():
    return {
        "tier_1_core": {"status": "stable", "tools": []},
        "tier_2_advanced": {"status": "experimental", "tools": []},
        "tier_3_admin": {"status": "guarded", "tools": []},
    }
"""
    errors = module._check_tier_status_parity(
        transport_src,
        gateway_src,
        {"stable", "active", "guarded"},
    )
    assert any("tier status values must be in" in err or "tier status drift" in err for err in errors)
