from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


def _load_http_error_adapter_parity_module():
    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "scripts" / "check_http_error_adapter_parity.py"
    spec = importlib.util.spec_from_file_location(
        "check_http_error_adapter_parity", script_path
    )
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_http_error_adapter_parity_guardrail_passes_for_current_sources() -> None:
    module = _load_http_error_adapter_parity_module()
    assert module.main() == 0


def test_http_error_adapter_parity_detects_defaults_key_drift() -> None:
    module = _load_http_error_adapter_parity_module()
    contract = module._load_contract()
    required_default_keys = {str(item) for item in contract["required_defaults_keys"]}
    src = """
_DEFAULTS = {"status_labels": {}, "fallback_5xx": "x", "fallback_other": "y"}

def backend_error_message(status_code, detail):
    detail_text = json.dumps(detail) if isinstance(detail, (dict, list)) else str(detail)
    detail_hints = _CONTRACT.get("detail_hints", {})
    return f"Backend {status_code}: {detail_text}"

def backend_request_failure_message(error):
    return "Backend request failed: upstream unavailable"
"""
    errors = module._check_source(src, "x", required_default_keys)
    assert any("_DEFAULTS keys drift" in err for err in errors)


def test_http_error_adapter_parity_detects_missing_json_dumps() -> None:
    module = _load_http_error_adapter_parity_module()
    contract = module._load_contract()
    required_default_keys = {str(item) for item in contract["required_defaults_keys"]}
    src = """
_DEFAULTS = {"status_labels": {}, "fallback_5xx": "x", "fallback_other": "y", "detail_hints": {}}

def backend_error_message(status_code, detail):
    detail_text = str(detail)
    detail_hints = _CONTRACT.get("detail_hints", {})
    return f"Backend {status_code}: {detail_text}"

def backend_request_failure_message(error):
    return "Backend request failed: upstream unavailable"
"""
    errors = module._check_source(src, "x", required_default_keys)
    assert any("json.dumps" in err for err in errors)


def test_http_error_adapter_guardrail_contract_loader_validates_required_keys(
    tmp_path: Path,
) -> None:
    module = _load_http_error_adapter_parity_module()
    broken = tmp_path / "http_error_adapter_guardrail_contract.json"
    broken.write_text("{}", encoding="utf-8")
    old_contract = module.CONTRACT
    module.CONTRACT = broken
    try:
        try:
            module._load_contract()
            assert False, "expected ValueError for invalid http error adapter contract"
        except ValueError as exc:
            assert "required_defaults_keys" in str(exc)
    finally:
        module.CONTRACT = old_contract
