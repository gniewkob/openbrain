#!/usr/bin/env python3
"""Guardrail: keep hidden test-data alert semantics aligned across runtime/docs."""

from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
RUNTIME_ALERTS = ROOT / "monitoring" / "prometheus" / "openbrain-alerts.yml"
DOC_ALERTS = ROOT / "docs" / "prometheus-alerts.yml"

ALERT_PRESENT = "OpenBrainHiddenTestDataPresent"
ALERT_SHARE = "OpenBrainHiddenTestDataShareHigh"


def _parse_alert_exprs(path: Path) -> dict[str, str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    alert_exprs: dict[str, str] = {}
    current_alert: str | None = None

    idx = 0
    while idx < len(lines):
        line = lines[idx]
        stripped = line.strip()
        if stripped.startswith("- alert:"):
            current_alert = stripped.split(":", 1)[1].strip()
            idx += 1
            continue
        if stripped.startswith("expr:") and current_alert:
            expr = stripped.split(":", 1)[1].strip()
            expr_indent = len(line) - len(line.lstrip(" "))
            if expr in {"|", ">"}:
                block_lines: list[str] = []
                idx += 1
                while idx < len(lines):
                    block_line = lines[idx]
                    if not block_line.strip():
                        idx += 1
                        continue
                    block_indent = len(block_line) - len(block_line.lstrip(" "))
                    if block_indent <= expr_indent:
                        break
                    block_lines.append(block_line.strip())
                    idx += 1
                expr = " ".join(block_lines).strip()
            else:
                idx += 1
            alert_exprs[current_alert] = expr
            current_alert = None
            continue
        idx += 1
    return alert_exprs


def _normalize_expr(expr: str) -> str:
    no_job = re.sub(r'\{job="openbrain-unified"\}', "", expr)
    return re.sub(r"\s+", "", no_job)


def _is_valid_present_expr(expr: str) -> bool:
    return _normalize_expr(expr) == "hidden_test_data_active_total>0"


def _is_valid_share_expr(expr: str) -> bool:
    normalized = _normalize_expr(expr)
    allowed = {
        "openbrain_hidden_test_data_share_active>=0.25",
        "hidden_test_data_active_total/clamp_min(active_memories_all_total,1)>=0.25",
    }
    return normalized in allowed


def main() -> int:
    errors: list[str] = []
    runtime = _parse_alert_exprs(RUNTIME_ALERTS)
    docs = _parse_alert_exprs(DOC_ALERTS)

    for source_name, source_map in (("runtime", runtime), ("docs", docs)):
        if ALERT_PRESENT not in source_map:
            errors.append(f"{source_name} alerts must include {ALERT_PRESENT}")
        if ALERT_SHARE not in source_map:
            errors.append(f"{source_name} alerts must include {ALERT_SHARE}")

    runtime_present = runtime.get(ALERT_PRESENT, "")
    runtime_share = runtime.get(ALERT_SHARE, "")
    docs_present = docs.get(ALERT_PRESENT, "")
    docs_share = docs.get(ALERT_SHARE, "")

    if runtime_present and not _is_valid_present_expr(runtime_present):
        errors.append(
            f"runtime {ALERT_PRESENT} expr must be hidden_test_data_active_total > 0 "
            f"(got: {runtime_present})"
        )
    if docs_present and not _is_valid_present_expr(docs_present):
        errors.append(
            f"docs {ALERT_PRESENT} expr must be hidden_test_data_active_total > 0 "
            f"(got: {docs_present})"
        )
    if runtime_share and not _is_valid_share_expr(runtime_share):
        errors.append(
            f"runtime {ALERT_SHARE} expr must encode 25% threshold "
            f"(got: {runtime_share})"
        )
    if docs_share and not _is_valid_share_expr(docs_share):
        errors.append(
            f"docs {ALERT_SHARE} expr must encode 25% threshold "
            f"(got: {docs_share})"
        )

    if errors:
        print("Hidden test-data alert parity guardrail failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print("Hidden test-data alert parity guardrail passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
