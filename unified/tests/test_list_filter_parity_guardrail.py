from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


def _load_list_filter_parity_module():
    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "scripts" / "check_list_filter_parity.py"
    spec = importlib.util.spec_from_file_location(
        "check_list_filter_parity", script_path
    )
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_list_filter_parity_guardrail_passes_for_current_sources() -> None:
    module = _load_list_filter_parity_module()
    assert module.main() == 0


def test_list_filter_parity_detects_missing_tenant_filter() -> None:
    module = _load_list_filter_parity_module()
    transport_src = """
async def brain_list():
    filters = build_list_filters(
        domain=domain,
        entity_type=entity_type,
        status=status,
        sensitivity=sensitivity,
        owner=owner,
        tenant_id=tenant_id,
        include_test_data=include_test_data,
    )
"""
    gateway_src = """
async def brain_list():
    filters = build_list_filters(
        domain=domain,
        entity_type=entity_type,
        status=status,
        sensitivity=sensitivity,
        owner=owner,
        include_test_data=include_test_data,
    )
"""
    errors = module._check_list_filter_parity(transport_src, gateway_src)
    assert any("brain_list build_list_filters keyword drift" in err for err in errors)
