from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


def _load_dashboard_memory_semantics_module():
    repo_root = Path(__file__).resolve().parents[2]
    script_path = repo_root / "scripts" / "check_dashboard_memory_semantics.py"
    spec = importlib.util.spec_from_file_location(
        "check_dashboard_memory_semantics", script_path
    )
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_dashboard_memory_semantics_guardrail_passes_for_current_dashboard() -> None:
    module = _load_dashboard_memory_semantics_module()
    assert module.main() == 0


def test_dashboard_memory_semantics_detects_wrong_active_expr(tmp_path: Path) -> None:
    module = _load_dashboard_memory_semantics_module()
    dashboard = tmp_path / "dashboard.json"
    dashboard.write_text(
        json.dumps(
            {
                "panels": [
                    {
                        "title": module.ACTIVE_TITLE,
                        "targets": [{"expr": 'active_memories_total{job="openbrain-unified"}'}],
                    },
                    {
                        "title": module.HIDDEN_TITLE,
                        "targets": [{"expr": module.HIDDEN_EXPR}],
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    original = module.DASHBOARD
    module.DASHBOARD = dashboard
    try:
        assert module.main() == 1
    finally:
        module.DASHBOARD = original


def test_dashboard_memory_semantics_detects_missing_panel(tmp_path: Path) -> None:
    module = _load_dashboard_memory_semantics_module()
    dashboard = tmp_path / "dashboard.json"
    dashboard.write_text(json.dumps({"panels": []}), encoding="utf-8")
    original = module.DASHBOARD
    module.DASHBOARD = dashboard
    try:
        assert module.main() == 1
    finally:
        module.DASHBOARD = original
