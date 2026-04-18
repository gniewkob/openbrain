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


def _load_required_panels(module) -> list[dict[str, str]]:
    _, panels = module._load_contract()
    return panels


def _panel_spec(panels: list[dict[str, str]], title: str) -> dict[str, str]:
    for panel in panels:
        if panel["title"] == title:
            return panel
    assert False, f"missing panel spec for title {title!r}"


def test_dashboard_memory_semantics_guardrail_passes_for_current_dashboard() -> None:
    module = _load_dashboard_memory_semantics_module()
    assert module.main() == 0


def test_dashboard_memory_semantics_detects_wrong_active_expr(tmp_path: Path) -> None:
    module = _load_dashboard_memory_semantics_module()
    panels = _load_required_panels(module)
    active = _panel_spec(panels, "Active Memories (All incl Test Data)")
    visible = _panel_spec(panels, "Active Memories (Visible Excl Test Data)")
    hidden = _panel_spec(panels, "Hidden Test Data (Active Only)")
    hidden_share = _panel_spec(panels, "Hidden Test Data Share (Active)")
    dashboard = tmp_path / "dashboard.json"
    dashboard.write_text(
        json.dumps(
            {
                "panels": [
                    {
                        "title": visible["title"],
                        "targets": [{"expr": visible["expr"]}],
                    },
                    {
                        "title": active["title"],
                        "targets": [
                            {"expr": 'active_memories_total{job="openbrain-unified"}'}
                        ],
                    },
                    {
                        "title": hidden["title"],
                        "targets": [{"expr": hidden["expr"]}],
                    },
                    {
                        "title": hidden_share["title"],
                        "targets": [{"expr": hidden_share["expr"]}],
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    contract = tmp_path / "dashboard-memory-contract.json"
    contract.write_text(
        json.dumps(
            {
                "dashboard_path": str(dashboard),
                "required_panels": panels,
            }
        ),
        encoding="utf-8",
    )
    original_contract = module.CONTRACT
    module.CONTRACT = contract
    try:
        assert module.main() == 1
    finally:
        module.CONTRACT = original_contract


def test_dashboard_memory_semantics_detects_missing_panel(tmp_path: Path) -> None:
    module = _load_dashboard_memory_semantics_module()
    panels = _load_required_panels(module)
    dashboard = tmp_path / "dashboard.json"
    dashboard.write_text(json.dumps({"panels": []}), encoding="utf-8")
    contract = tmp_path / "dashboard-memory-contract.json"
    contract.write_text(
        json.dumps(
            {
                "dashboard_path": str(dashboard),
                "required_panels": panels,
            }
        ),
        encoding="utf-8",
    )
    original_contract = module.CONTRACT
    module.CONTRACT = contract
    try:
        assert module.main() == 1
    finally:
        module.CONTRACT = original_contract


def test_dashboard_memory_semantics_detects_wrong_visible_expr(tmp_path: Path) -> None:
    module = _load_dashboard_memory_semantics_module()
    panels = _load_required_panels(module)
    active = _panel_spec(panels, "Active Memories (All incl Test Data)")
    visible = _panel_spec(panels, "Active Memories (Visible Excl Test Data)")
    hidden = _panel_spec(panels, "Hidden Test Data (Active Only)")
    hidden_share = _panel_spec(panels, "Hidden Test Data Share (Active)")
    dashboard = tmp_path / "dashboard.json"
    dashboard.write_text(
        json.dumps(
            {
                "panels": [
                    {
                        "title": visible["title"],
                        "targets": [
                            {
                                "expr": 'active_memories_all_total{job="openbrain-unified"}'
                            }
                        ],
                    },
                    {
                        "title": active["title"],
                        "targets": [{"expr": active["expr"]}],
                    },
                    {
                        "title": hidden["title"],
                        "targets": [{"expr": hidden["expr"]}],
                    },
                    {
                        "title": hidden_share["title"],
                        "targets": [{"expr": hidden_share["expr"]}],
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    contract = tmp_path / "dashboard-memory-contract.json"
    contract.write_text(
        json.dumps(
            {
                "dashboard_path": str(dashboard),
                "required_panels": panels,
            }
        ),
        encoding="utf-8",
    )
    original_contract = module.CONTRACT
    module.CONTRACT = contract
    try:
        assert module.main() == 1
    finally:
        module.CONTRACT = original_contract


def test_dashboard_memory_semantics_detects_wrong_hidden_share_expr(
    tmp_path: Path,
) -> None:
    module = _load_dashboard_memory_semantics_module()
    panels = _load_required_panels(module)
    active = _panel_spec(panels, "Active Memories (All incl Test Data)")
    visible = _panel_spec(panels, "Active Memories (Visible Excl Test Data)")
    hidden = _panel_spec(panels, "Hidden Test Data (Active Only)")
    hidden_share = _panel_spec(panels, "Hidden Test Data Share (Active)")
    dashboard = tmp_path / "dashboard.json"
    dashboard.write_text(
        json.dumps(
            {
                "panels": [
                    {
                        "title": visible["title"],
                        "targets": [{"expr": visible["expr"]}],
                    },
                    {
                        "title": active["title"],
                        "targets": [{"expr": active["expr"]}],
                    },
                    {
                        "title": hidden["title"],
                        "targets": [{"expr": hidden["expr"]}],
                    },
                    {
                        "title": hidden_share["title"],
                        "targets": [
                            {
                                "expr": 'hidden_test_data_active_total{job="openbrain-unified"}'
                            }
                        ],
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    contract = tmp_path / "dashboard-memory-contract.json"
    contract.write_text(
        json.dumps(
            {
                "dashboard_path": str(dashboard),
                "required_panels": panels,
            }
        ),
        encoding="utf-8",
    )
    original_contract = module.CONTRACT
    module.CONTRACT = contract
    try:
        assert module.main() == 1
    finally:
        module.CONTRACT = original_contract


def test_dashboard_memory_semantics_contract_loader_validates_shape(
    tmp_path: Path,
) -> None:
    module = _load_dashboard_memory_semantics_module()
    broken = tmp_path / "dashboard-memory-contract.json"
    broken.write_text("{}", encoding="utf-8")

    original_contract = module.CONTRACT
    module.CONTRACT = broken
    try:
        try:
            module._load_contract()
            assert False, "expected ValueError for invalid contract shape"
        except ValueError as exc:
            assert "dashboard_path" in str(exc)
    finally:
        module.CONTRACT = original_contract
