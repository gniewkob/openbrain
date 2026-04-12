from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


def _load_guardrail_module():
    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "scripts" / "check_mcp_transport_import_scope.py"
    spec = importlib.util.spec_from_file_location(
        "check_mcp_transport_import_scope", script_path
    )
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_mcp_transport_import_scope_guardrail_passes_for_current_sources() -> None:
    module = _load_guardrail_module()
    assert module.main() == 0


def test_import_scope_rejects_non_test_importers() -> None:
    module = _load_guardrail_module()
    contract = module._load_contract()
    errors = module._check_import_scope(
        ["unified/src/combined.py", "unified/src/api/v1/memory.py"],
        contract,
    )
    assert any("outside approved scope" in err for err in errors)


def test_import_scope_requires_combined_import() -> None:
    module = _load_guardrail_module()
    contract = module._load_contract()
    errors = module._check_import_scope(["unified/tests/test_mcp_transport.py"], contract)
    assert "unified/src/combined.py must import mcp_transport" in errors


def test_import_scope_contract_loader_validates_required_keys(tmp_path: Path) -> None:
    module = _load_guardrail_module()
    broken = tmp_path / "contract.json"
    broken.write_text("{}", encoding="utf-8")

    old_contract = module.CONTRACT
    module.CONTRACT = broken
    try:
        try:
            module._load_contract()
            assert False, "expected ValueError for missing contract keys"
        except ValueError as exc:
            assert "missing keys" in str(exc)
    finally:
        module.CONTRACT = old_contract
