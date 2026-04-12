from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


def _load_admin_endpoint_contract_parity_module():
    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "scripts" / "check_admin_endpoint_contract_parity.py"
    spec = importlib.util.spec_from_file_location(
        "check_admin_endpoint_contract_parity", script_path
    )
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_admin_endpoint_contract_parity_guardrail_passes_for_current_sources() -> None:
    module = _load_admin_endpoint_contract_parity_module()
    assert module.main() == 0


def test_admin_endpoint_contract_parity_detects_payload_key_drift() -> None:
    module = _load_admin_endpoint_contract_parity_module()
    checked_tools = ["brain_cleanup_build_test_data"]
    transport_src = """
async def brain_cleanup_build_test_data(dry_run: bool = True, limit: int = 100):
    return await _safe_req(
        "POST",
        memory_path("cleanup_build_test_data"),
        json={"dry_run": dry_run, "limit": limit},
    )
"""
    gateway_src = """
async def brain_cleanup_build_test_data(dry_run: bool = True, limit: int = 100):
    async with _client() as c:
        r = await _request_or_raise(
            c,
            "POST",
            memory_absolute_path("cleanup_build_test_data"),
            json={"dry_run": dry_run, "max_items": limit},
        )
        return r.json()
"""
    errors = module._check_admin_endpoint_contract_parity(
        transport_src, gateway_src, checked_tools
    )
    assert any("brain_cleanup_build_test_data endpoint contract drift" in err for err in errors)


def test_admin_endpoint_guardrail_contract_loader_validates_shape(tmp_path: Path) -> None:
    module = _load_admin_endpoint_contract_parity_module()
    broken = tmp_path / "admin_endpoint_guardrail_contract.json"
    broken.write_text("{}", encoding="utf-8")
    old_contract = module.CONTRACT
    module.CONTRACT = broken
    try:
        try:
            module._load_contract()
            assert False, "expected ValueError for invalid admin endpoint contract"
        except ValueError as exc:
            assert "checked_tools" in str(exc)
    finally:
        module.CONTRACT = old_contract
