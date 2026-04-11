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
    old_runtime = module.RUNTIME_ALERTS
    old_docs = module.DOC_ALERTS
    module.RUNTIME_ALERTS = runtime
    module.DOC_ALERTS = docs
    try:
        assert module.main() == 1
    finally:
        module.RUNTIME_ALERTS = old_runtime
        module.DOC_ALERTS = old_docs


def test_hidden_test_data_alert_parity_detects_wrong_threshold(tmp_path: Path) -> None:
    module = _load_module()
    runtime = tmp_path / "runtime.yml"
    docs = tmp_path / "docs.yml"
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
    old_runtime = module.RUNTIME_ALERTS
    old_docs = module.DOC_ALERTS
    module.RUNTIME_ALERTS = runtime
    module.DOC_ALERTS = docs
    try:
        assert module.main() == 1
    finally:
        module.RUNTIME_ALERTS = old_runtime
        module.DOC_ALERTS = old_docs
