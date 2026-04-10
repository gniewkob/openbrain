from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


def _load_update_audit_semantics_parity_module():
    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "scripts" / "check_update_audit_semantics_parity.py"
    spec = importlib.util.spec_from_file_location(
        "check_update_audit_semantics_parity", script_path
    )
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_update_audit_semantics_parity_guardrail_passes_for_current_sources() -> None:
    module = _load_update_audit_semantics_parity_module()
    assert module.main() == 0


def test_update_audit_semantics_detects_missing_normalize_call() -> None:
    module = _load_update_audit_semantics_parity_module()
    src = """
async def brain_update(memory_id, content, updated_by="agent"):
    return _safe_req("PATCH", "/x", json={"content": content, "updated_by": canonical_updated_by()})
"""
    errors = module._check_update_semantics(src, "x")
    assert any("normalize_updated_by" in err for err in errors)


def test_update_audit_semantics_detects_non_canonical_payload_actor() -> None:
    module = _load_update_audit_semantics_parity_module()
    src = """
async def brain_update(memory_id, content, updated_by="agent"):
    _ = normalize_updated_by(updated_by)
    return _safe_req("PATCH", "/x", json={"content": content, "updated_by": updated_by})
"""
    errors = module._check_update_semantics(src, "x")
    assert any("canonical_updated_by" in err for err in errors)
