from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


def _load_search_filter_parity_module():
    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "scripts" / "check_search_filter_parity.py"
    spec = importlib.util.spec_from_file_location(
        "check_search_filter_parity", script_path
    )
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_search_filter_parity_guardrail_passes_for_current_sources() -> None:
    module = _load_search_filter_parity_module()
    assert module.main() == 0


def test_search_filter_parity_detects_missing_owner_filter() -> None:
    module = _load_search_filter_parity_module()
    transport_src = """
async def brain_search():
    filters = build_list_filters(
        domain=domain,
        entity_type=entity_type,
        owner=owner,
        sensitivity=sensitivity,
        include_test_data=include_test_data,
    )
"""
    gateway_src = """
async def brain_search():
    filters = build_list_filters(
        domain=domain,
        entity_type=entity_type,
        sensitivity=sensitivity,
        include_test_data=include_test_data,
    )
"""
    errors = module._check_search_filter_parity(transport_src, gateway_src)
    assert any("brain_search build_list_filters keyword drift" in err for err in errors)
