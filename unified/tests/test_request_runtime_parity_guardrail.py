from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


def _load_request_runtime_parity_module():
    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "scripts" / "check_request_runtime_parity.py"
    spec = importlib.util.spec_from_file_location(
        "check_request_runtime_parity", script_path
    )
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_request_runtime_parity_guardrail_passes_for_current_sources() -> None:
    module = _load_request_runtime_parity_module()
    assert module.main() == 0


def test_request_runtime_parity_guardrail_detects_request_validation_drift() -> None:
    module = _load_request_runtime_parity_module()
    http_src = """
def _validate_request_contracts(data):
    if not isinstance(data, dict):
        raise ValueError("request_contracts must be a JSON object")
    return data

def _load_request_contracts():
    path = Path(__file__).resolve() / "contracts" / "request_contracts.json"
"""
    gateway_src = """
def _validate_request_contracts(data):
    if not isinstance(data, dict):
        raise ValueError("request_contracts must be JSON")
    return data

def _load_request_contracts():
    path = Path(__file__).resolve() / "contracts" / "request_contracts.json"
"""
    errors = module._check_request_contract_parity(http_src, gateway_src)
    assert any("_validate_request_contracts logic must stay identical" in err for err in errors)


def test_request_runtime_parity_guardrail_detects_runtime_defaults_drift() -> None:
    module = _load_request_runtime_parity_module()
    http_src = """
_DEFAULTS = {"max_search_top_k": 100}
def _validate_runtime_limits(data):
    if not isinstance(data, dict):
        raise ValueError("runtime_limits must be a JSON object")
    return data
def load_runtime_limits():
    path = Path(__file__).resolve() / "contracts" / "runtime_limits.json"
"""
    gateway_src = """
_DEFAULTS = {"max_search_top_k": 200}
def _validate_runtime_limits(data):
    if not isinstance(data, dict):
        raise ValueError("runtime_limits must be a JSON object")
    return data
def load_runtime_limits():
    path = Path(__file__).resolve() / "contracts" / "runtime_limits.json"
"""
    errors = module._check_runtime_limits_parity(http_src, gateway_src)
    assert any("_DEFAULTS must stay identical" in err for err in errors)
