from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


def _load_http_error_contract_semantics_module():
    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "scripts" / "check_http_error_contract_semantics.py"
    spec = importlib.util.spec_from_file_location(
        "check_http_error_contract_semantics", script_path
    )
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_http_error_contract_semantics_guardrail_passes_for_current_contract() -> None:
    module = _load_http_error_contract_semantics_module()
    assert module.main() == 0


def test_http_error_contract_semantics_detects_missing_session_hint_drift() -> None:
    module = _load_http_error_contract_semantics_module()
    bad = {
        "status_labels": {
            "401": "Authentication required",
            "403": "Access denied",
            "404": "Resource not found",
            "422": "Validation error",
        },
        "detail_hints": {
            "missing_session_id": {
                "status_code": 400,
                "contains": "Session missing",
                "message": "Different message",
            }
        },
        "fallback_5xx": "Internal server error",
        "fallback_other": "Request failed",
    }

    errors = module._check_contract(bad)
    assert any("detail_hints.missing_session_id.contains drift" in err for err in errors)
    assert any("detail_hints.missing_session_id.message drift" in err for err in errors)
