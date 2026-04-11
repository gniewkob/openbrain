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
    module.CHECKED_TOOLS = ("brain_cleanup_build_test_data",)
    errors = module._check_admin_endpoint_contract_parity(transport_src, gateway_src)
    assert any("brain_cleanup_build_test_data endpoint contract drift" in err for err in errors)
