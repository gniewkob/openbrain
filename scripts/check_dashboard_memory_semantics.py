#!/usr/bin/env python3
"""Guardrail: keep OpenBrain memory dashboard panel semantics truthful."""

from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DASHBOARD = ROOT / "monitoring/grafana/dashboards/openbrain/openbrain-overview.json"

ACTIVE_TITLE = "Active Memories (All incl Test Data)"
ACTIVE_EXPR = 'active_memories_all_total{job="openbrain-unified"}'
HIDDEN_TITLE = "Hidden Test Data (Active Only)"
HIDDEN_EXPR = 'hidden_test_data_active_total{job="openbrain-unified"}'


def _fail(message: str) -> int:
    print(f"[FAIL] {message}", file=sys.stderr)
    return 1


def _extract_panel_expr(panel: dict[str, object]) -> str | None:
    targets = panel.get("targets")
    if not isinstance(targets, list) or not targets:
        return None
    first = targets[0]
    if not isinstance(first, dict):
        return None
    expr = first.get("expr")
    return expr if isinstance(expr, str) else None


def _find_panel_by_title(payload: dict[str, object], title: str) -> dict[str, object] | None:
    panels = payload.get("panels")
    if not isinstance(panels, list):
        return None
    for panel in panels:
        if isinstance(panel, dict) and panel.get("title") == title:
            return panel
    return None


def main() -> int:
    payload = json.loads(DASHBOARD.read_text(encoding="utf-8"))
    errors: list[str] = []

    active_panel = _find_panel_by_title(payload, ACTIVE_TITLE)
    if active_panel is None:
        errors.append(f"missing dashboard panel title: {ACTIVE_TITLE}")
    else:
        active_expr = _extract_panel_expr(active_panel)
        if active_expr != ACTIVE_EXPR:
            errors.append(
                f"{ACTIVE_TITLE} must use expr {ACTIVE_EXPR!r} (got {active_expr!r})"
            )

    hidden_panel = _find_panel_by_title(payload, HIDDEN_TITLE)
    if hidden_panel is None:
        errors.append(f"missing dashboard panel title: {HIDDEN_TITLE}")
    else:
        hidden_expr = _extract_panel_expr(hidden_panel)
        if hidden_expr != HIDDEN_EXPR:
            errors.append(
                f"{HIDDEN_TITLE} must use expr {HIDDEN_EXPR!r} (got {hidden_expr!r})"
            )

    if errors:
        for error in errors:
            _fail(error)
        return 1
    print("Dashboard memory semantics guardrail passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
