from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


def _load_tool_signature_parity_module():
    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "scripts" / "check_tool_signature_parity.py"
    spec = importlib.util.spec_from_file_location(
        "check_tool_signature_parity", script_path
    )
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_tool_signature_parity_guardrail_passes_for_current_sources() -> None:
    module = _load_tool_signature_parity_module()
    assert module.main() == 0


def test_tool_signature_parity_detects_parameter_order_drift() -> None:
    module = _load_tool_signature_parity_module()
    checked_tools = ["brain_update"]
    transport_src = """
async def brain_update(memory_id, content, updated_by="agent", title=None):
    return {}
"""
    gateway_src = """
async def brain_update(memory_id, content, title=None, updated_by="agent"):
    return {}
"""
    errors = module._check_signature_parity(transport_src, gateway_src, checked_tools)
    assert any("brain_update signature drift" in err for err in errors)


def test_tool_signature_guardrail_contract_loader_validates_shape(
    tmp_path: Path,
) -> None:
    module = _load_tool_signature_parity_module()
    broken = tmp_path / "tool_signature_guardrail_contract.json"
    broken.write_text("{}", encoding="utf-8")
    old_contract = module.CONTRACT
    module.CONTRACT = broken
    try:
        try:
            module._load_contract()
            assert False, "expected ValueError for invalid tool signature contract"
        except ValueError as exc:
            assert "checked_tools" in str(exc)
    finally:
        module.CONTRACT = old_contract
