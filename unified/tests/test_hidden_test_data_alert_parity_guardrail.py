from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


def _load_module():
    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "scripts" / "check_hidden_test_data_alert_parity.py"
    spec = importlib.util.spec_from_file_location(
        "check_hidden_test_data_alert_parity", script_path
    )
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_hidden_test_data_alert_parity_guardrail_passes_for_current_sources() -> None:
    module = _load_module()
    assert module.main() == 0


def test_hidden_test_data_alert_parity_detects_missing_alert(tmp_path: Path) -> None:
    module = _load_module()
    runtime = tmp_path / "runtime.yml"
    docs = tmp_path / "docs.yml"
    contract = tmp_path / "contract.json"
    runtime.write_text(
        """
groups:
  - name: openbrain-alerts
    rules:
      - alert: OpenBrainHiddenTestDataPresent
        expr: hidden_test_data_active_total{job="openbrain-unified"} > 0
""",
        encoding="utf-8",
    )
    docs.write_text(
        """
groups:
  - name: openbrain-governance
    rules:
      - alert: OpenBrainHiddenTestDataPresent
        expr: hidden_test_data_active_total > 0
""",
        encoding="utf-8",
    )
    contract.write_text(
        """
{
  "runtime_alerts_path": "runtime.yml",
  "docs_alerts_path": "docs.yml",
  "alerts": {
    "present": {"name": "OpenBrainHiddenTestDataPresent", "allowed_exprs": ["hidden_test_data_active_total > 0"]},
    "share_high": {"name": "OpenBrainHiddenTestDataShareHigh", "allowed_exprs": ["openbrain_hidden_test_data_share_active >= 0.25"]}
  }
}
""",
        encoding="utf-8",
    )
    old_root = module.ROOT
    old_contract = module.CONTRACT
    module.ROOT = tmp_path
    module.CONTRACT = contract
    try:
        assert module.main() == 1
    finally:
        module.ROOT = old_root
        module.CONTRACT = old_contract


def test_hidden_test_data_alert_parity_detects_wrong_threshold(tmp_path: Path) -> None:
    module = _load_module()
    runtime = tmp_path / "runtime.yml"
    docs = tmp_path / "docs.yml"
    contract = tmp_path / "contract.json"
    runtime.write_text(
        """
groups:
  - name: openbrain-alerts
    rules:
      - alert: OpenBrainHiddenTestDataPresent
        expr: hidden_test_data_active_total{job="openbrain-unified"} > 0
      - alert: OpenBrainHiddenTestDataShareHigh
        expr: openbrain_hidden_test_data_share_active >= 0.50
""",
        encoding="utf-8",
    )
    docs.write_text(
        """
groups:
  - name: openbrain-governance
    rules:
      - alert: OpenBrainHiddenTestDataPresent
        expr: hidden_test_data_active_total > 0
      - alert: OpenBrainHiddenTestDataShareHigh
        expr: hidden_test_data_active_total / clamp_min(active_memories_all_total, 1) >= 0.25
""",
        encoding="utf-8",
    )
    contract.write_text(
        """
{
  "runtime_alerts_path": "runtime.yml",
  "docs_alerts_path": "docs.yml",
  "alerts": {
    "present": {"name": "OpenBrainHiddenTestDataPresent", "allowed_exprs": ["hidden_test_data_active_total > 0"]},
    "share_high": {
      "name": "OpenBrainHiddenTestDataShareHigh",
      "allowed_exprs": [
        "openbrain_hidden_test_data_share_active >= 0.25",
        "hidden_test_data_active_total / clamp_min(active_memories_all_total, 1) >= 0.25"
      ]
    }
  }
}
""",
        encoding="utf-8",
    )
    old_root = module.ROOT
    old_contract = module.CONTRACT
    module.ROOT = tmp_path
    module.CONTRACT = contract
    try:
        assert module.main() == 1
    finally:
        module.ROOT = old_root
        module.CONTRACT = old_contract


def test_hidden_test_data_alert_contract_loader_validates_shape(tmp_path: Path) -> None:
    module = _load_module()
    broken = tmp_path / "hidden_test_data_alert_guardrail_contract.json"
    broken.write_text("{}", encoding="utf-8")
    old_contract = module.CONTRACT
    module.CONTRACT = broken
    try:
        try:
            module._load_contract()
            assert False, "expected ValueError for invalid hidden test data contract"
        except ValueError as exc:
            assert "runtime_alerts_path" in str(exc)
    finally:
        module.CONTRACT = old_contract
