from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


def _load_export_contract_module():
    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "scripts" / "check_export_contract.py"
    spec = importlib.util.spec_from_file_location("check_export_contract", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_export_contract_guardrail_passes_for_current_sources() -> None:
    module = _load_export_contract_module()
    assert module.main() == 0


def test_export_contract_guardrail_helpers_detect_missing_restricted_fallback() -> None:
    module = _load_export_contract_module()
    src = """
EXPORT_POLICY = {
  "public": {"allow_fields": None, "redact_content": False, "allow_tags": True, "allow_match_key": True},
  "internal": {"allow_fields": set(), "redact_content": True, "allow_tags": True, "allow_match_key": True},
  "confidential": {"allow_fields": set(), "redact_content": True, "allow_tags": False, "allow_match_key": False},
  "restricted": {"allow_fields": set(), "redact_content": True, "allow_tags": False, "allow_match_key": False},
}

def _export_record(record, sensitivity, role):
  policy = EXPORT_POLICY.get(sensitivity)
  return {}
"""
    errors = module._check_export_policy_semantics(src)
    assert any("fallback to restricted policy" in err for err in errors)
