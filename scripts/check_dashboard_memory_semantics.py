#!/usr/bin/env python3
"""Guardrail: keep OpenBrain memory dashboard panel semantics truthful."""

from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
CONTRACT = ROOT / "unified/contracts/dashboard_memory_semantics_guardrail_contract.json"


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


def _load_contract() -> tuple[Path, list[dict[str, str]]]:
    payload = json.loads(CONTRACT.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("dashboard memory semantics contract must be a JSON object")

    dashboard_path_raw = payload.get("dashboard_path")
    if not isinstance(dashboard_path_raw, str) or not dashboard_path_raw.strip():
        raise ValueError("contract dashboard_path must be a non-empty string")
    dashboard_path = ROOT / dashboard_path_raw

    required_panels = payload.get("required_panels")
    if not isinstance(required_panels, list) or not required_panels:
        raise ValueError("contract required_panels must be a non-empty list")

    normalized_panels: list[dict[str, str]] = []
    for panel in required_panels:
        if not isinstance(panel, dict):
            raise ValueError("contract required_panels items must be objects")
        title = panel.get("title")
        expr = panel.get("expr")
        if not isinstance(title, str) or not title:
            raise ValueError("contract required_panels.title must be non-empty string")
        if not isinstance(expr, str) or not expr:
            raise ValueError("contract required_panels.expr must be non-empty string")
        normalized_panels.append({"title": title, "expr": expr})

    return dashboard_path, normalized_panels


def main() -> int:
    try:
        dashboard_path, required_panels = _load_contract()
    except Exception as exc:
        return _fail(f"failed to load dashboard memory semantics contract: {exc}")

    payload = json.loads(dashboard_path.read_text(encoding="utf-8"))
    errors: list[str] = []

    for spec in required_panels:
        title = spec["title"]
        expected_expr = spec["expr"]
        panel = _find_panel_by_title(payload, title)
        if panel is None:
            errors.append(f"missing dashboard panel title: {title}")
            continue
        actual_expr = _extract_panel_expr(panel)
        if actual_expr != expected_expr:
            errors.append(
                f"{title} must use expr {expected_expr!r} (got {actual_expr!r})"
            )

    if errors:
        for error in errors:
            _fail(error)
        return 1
    print("Dashboard memory semantics guardrail passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
