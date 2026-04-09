from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


def _load_capabilities_manifest_parity_module():
    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "scripts" / "check_capabilities_manifest_parity.py"
    spec = importlib.util.spec_from_file_location(
        "check_capabilities_manifest_parity", script_path
    )
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_capabilities_manifest_parity_guardrail_passes_for_current_sources() -> None:
    module = _load_capabilities_manifest_parity_module()
    assert module.main() == 0


def test_capabilities_manifest_parity_guardrail_detects_defaults_drift() -> None:
    module = _load_capabilities_manifest_parity_module()

    http_src = """
_DEFAULTS = {"core_tools": ["search"]}
def load_capabilities_manifest():
    manifest_path = Path(__file__).resolve() / "contracts" / "capabilities_manifest.json"
"""
    gateway_src = """
_DEFAULTS = {"core_tools": ["search", "get"]}
def load_capabilities_manifest():
    manifest_path = Path(__file__).resolve() / "contracts" / "capabilities_manifest.json"
"""
    errors = module._check_manifest_parity(http_src, gateway_src)
    assert any("_DEFAULTS must stay identical" in err for err in errors)
