from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


def _load_capabilities_metadata_parity_module():
    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "scripts" / "check_capabilities_metadata_parity.py"
    spec = importlib.util.spec_from_file_location(
        "check_capabilities_metadata_parity", script_path
    )
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_capabilities_metadata_parity_guardrail_passes_for_current_sources() -> None:
    module = _load_capabilities_metadata_parity_module()
    assert module.main() == 0


def test_capabilities_metadata_parity_guardrail_detects_semver_drift() -> None:
    module = _load_capabilities_metadata_parity_module()
    http_src = """
import re
_SEMVER = re.compile(r"^\\\\d+\\\\.\\\\d+\\\\.\\\\d+$")
def load_capabilities_metadata():
    contract_path = Path(__file__).resolve() / "contracts" / "capabilities_metadata.json"
"""
    gateway_src = """
import re
_SEMVER = re.compile(r"^v\\\\d+\\\\.\\\\d+\\\\.\\\\d+$")
def load_capabilities_metadata():
    contract_path = Path(__file__).resolve() / "contracts" / "capabilities_metadata.json"
"""
    errors = module._check_metadata_parity(http_src, gateway_src)
    assert any("_SEMVER pattern must stay identical" in err for err in errors)
