from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


def _load_backend_probe_contract_parity_module():
    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "scripts" / "check_backend_probe_contract_parity.py"
    spec = importlib.util.spec_from_file_location(
        "check_backend_probe_contract_parity", script_path
    )
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_backend_probe_contract_parity_guardrail_passes_for_current_sources() -> None:
    module = _load_backend_probe_contract_parity_module()
    assert module.main() == 0


def test_backend_probe_contract_parity_detects_readyz_order_drift() -> None:
    module = _load_backend_probe_contract_parity_module()
    transport_src = """
async def _get_backend_status():
    readyz_paths = ("/readyz", "/api/v1/readyz")
    return {"probe": "readyz", "reason": "/readyz probe failed; /healthz probe failed; /api/v1/health probe failed"}
"""
    gateway_src = """
async def _get_backend_status():
    readyz_paths = ("/api/v1/readyz", "/readyz")
    return {"probe": "readyz", "reason": "/readyz probe failed; /healthz probe failed; /api/v1/health probe failed"}
"""
    errors = module._check_backend_probe_contract_parity(transport_src, gateway_src)
    assert any(
        "readyz_paths drift" in err or "backend probe contract drift" in err
        for err in errors
    )


def test_backend_probe_contract_loader_validates_required_keys(tmp_path: Path) -> None:
    module = _load_backend_probe_contract_parity_module()
    broken = tmp_path / "backend_probe_guardrail_contract.json"
    broken.write_text("{}", encoding="utf-8")
    old_contract = module.CONTRACT
    module.CONTRACT = broken
    try:
        try:
            module._load_contract()
            assert False, (
                "expected ValueError for invalid backend probe guardrail contract"
            )
        except ValueError as exc:
            assert "readyz_paths" in str(exc)
    finally:
        module.CONTRACT = old_contract
