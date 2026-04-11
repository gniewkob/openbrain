from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


def _load_admin_bounds_parity_module():
    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "scripts" / "check_admin_bounds_parity.py"
    spec = importlib.util.spec_from_file_location(
        "check_admin_bounds_parity", script_path
    )
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_admin_bounds_parity_guardrail_passes_for_current_sources() -> None:
    module = _load_admin_bounds_parity_module()
    assert module.main() == 0


def test_admin_bounds_parity_detects_bounds_drift() -> None:
    module = _load_admin_bounds_parity_module()
    transport_src = """
async def brain_cleanup_build_test_data(dry_run: bool = True, limit: int = 100):
    if not 1 <= limit <= 500:
        raise ValueError("limit must be 1–500")
    return {}
"""
    gateway_src = """
async def brain_cleanup_build_test_data(dry_run: bool = True, limit: int = 100):
    if not 1 <= limit <= 600:
        raise ValueError("limit must be 1–600")
    return {}
"""
    module.CHECKED_BOUNDS = (("brain_cleanup_build_test_data", "limit"),)
    errors = module._check_admin_bounds_parity(transport_src, gateway_src)
    assert any("brain_cleanup_build_test_data.limit drift" in err for err in errors)
