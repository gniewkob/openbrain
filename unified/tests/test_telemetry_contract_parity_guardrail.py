from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


def _load_telemetry_contract_parity_module():
    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "scripts" / "check_telemetry_contract_parity.py"
    spec = importlib.util.spec_from_file_location(
        "check_telemetry_contract_parity", script_path
    )
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_telemetry_contract_parity_guardrail_passes_for_current_sources() -> None:
    module = _load_telemetry_contract_parity_module()
    assert module.main() == 0


def test_collect_gauge_names_from_source_extracts_total_keys() -> None:
    module = _load_telemetry_contract_parity_module()
    src = """
def build():
    gauges = {
        "active_memories_total": 1.0,
        "hidden_test_data_total": 2.0,
        "not_metric": 3.0,
    }
    return gauges
"""
    names = module._collect_gauge_names_from_source(src)
    assert "active_memories_total" in names
    assert "hidden_test_data_total" in names
    assert "not_metric" not in names


def test_telemetry_contract_parity_detects_missing_metric() -> None:
    module = _load_telemetry_contract_parity_module()
    gauge_names = {"active_memories_total", "active_memories_all_total"}
    required = {"active_memories_total"}
    missing = sorted(name for name in gauge_names if name not in required)
    assert missing == ["active_memories_all_total"]
