from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


def _load_capabilities_health_parity_module():
    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "scripts" / "check_capabilities_health_parity.py"
    spec = importlib.util.spec_from_file_location(
        "check_capabilities_health_parity", script_path
    )
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_capabilities_health_parity_guardrail_passes_for_current_sources() -> None:
    module = _load_capabilities_health_parity_module()
    assert module.main() == 0


def test_capabilities_health_parity_guardrail_detects_build_logic_drift() -> None:
    module = _load_capabilities_health_parity_module()
    http_src = """
def _api_component(api):
    return "healthy"
def _store_component(state):
    return "healthy"
def build_capabilities_health(backend, obsidian_status):
    return {"overall": "degraded"}
"""
    gateway_src = """
def _api_component(api):
    return "healthy"
def _store_component(state):
    return "healthy"
def build_capabilities_health(backend, obsidian_status):
    return {"overall": "healthy"}
"""
    errors = module._check_health_parity(http_src, gateway_src)
    assert any("build_capabilities_health logic must stay identical" in err for err in errors)
