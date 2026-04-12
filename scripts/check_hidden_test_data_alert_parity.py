#!/usr/bin/env python3
"""Guardrail: keep hidden test-data alert semantics aligned across runtime/docs."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
CONTRACT = ROOT / "unified/contracts/hidden_test_data_alert_guardrail_contract.json"


def _load_contract() -> dict[str, object]:
    payload = json.loads(CONTRACT.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("hidden_test_data_alert_guardrail_contract must be object")
    runtime_alerts_path = payload.get("runtime_alerts_path")
    docs_alerts_path = payload.get("docs_alerts_path")
    alerts = payload.get("alerts")
    if not isinstance(runtime_alerts_path, str) or not runtime_alerts_path:
        raise ValueError("contract runtime_alerts_path must be non-empty string")
    if not isinstance(docs_alerts_path, str) or not docs_alerts_path:
        raise ValueError("contract docs_alerts_path must be non-empty string")
    if not isinstance(alerts, dict):
        raise ValueError("contract alerts must be object")
    for key in ("present", "share_high"):
        spec = alerts.get(key)
        if not isinstance(spec, dict):
            raise ValueError(f"contract alerts.{key} must be object")
        name = spec.get("name")
        allowed_exprs = spec.get("allowed_exprs")
        if not isinstance(name, str) or not name:
            raise ValueError(f"contract alerts.{key}.name must be non-empty string")
        if (
            not isinstance(allowed_exprs, list)
            or not allowed_exprs
            or any(not isinstance(expr, str) or not expr for expr in allowed_exprs)
        ):
            raise ValueError(
                f"contract alerts.{key}.allowed_exprs must be non-empty list[str]"
            )
    return payload


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


def _is_expr_allowed(expr: str, allowed_exprs: list[str]) -> bool:
    normalized = _normalize_expr(expr)
    normalized_allowed = {_normalize_expr(item) for item in allowed_exprs}
    return normalized in normalized_allowed


def main() -> int:
    errors: list[str] = []
    contract = _load_contract()
    runtime_alerts = ROOT / str(contract["runtime_alerts_path"])
    docs_alerts = ROOT / str(contract["docs_alerts_path"])
    alerts = contract["alerts"]  # type: ignore[assignment]
    present = alerts["present"]  # type: ignore[index]
    share_high = alerts["share_high"]  # type: ignore[index]
    alert_present = str(present["name"])  # type: ignore[index]
    alert_share = str(share_high["name"])  # type: ignore[index]
    present_allowed_exprs = [str(item) for item in present["allowed_exprs"]]  # type: ignore[index]
    share_allowed_exprs = [str(item) for item in share_high["allowed_exprs"]]  # type: ignore[index]

    runtime = _parse_alert_exprs(runtime_alerts)
    docs = _parse_alert_exprs(docs_alerts)

    for source_name, source_map in (("runtime", runtime), ("docs", docs)):
        if alert_present not in source_map:
            errors.append(f"{source_name} alerts must include {alert_present}")
        if alert_share not in source_map:
            errors.append(f"{source_name} alerts must include {alert_share}")

    runtime_present = runtime.get(alert_present, "")
    runtime_share = runtime.get(alert_share, "")
    docs_present = docs.get(alert_present, "")
    docs_share = docs.get(alert_share, "")

    if runtime_present and not _is_expr_allowed(runtime_present, present_allowed_exprs):
        errors.append(
            f"runtime {alert_present} expr must match allowed contract expressions "
            f"(got: {runtime_present})"
        )
    if docs_present and not _is_expr_allowed(docs_present, present_allowed_exprs):
        errors.append(
            f"docs {alert_present} expr must match allowed contract expressions "
            f"(got: {docs_present})"
        )
    if runtime_share and not _is_expr_allowed(runtime_share, share_allowed_exprs):
        errors.append(
            f"runtime {alert_share} expr must match allowed contract expressions "
            f"(got: {runtime_share})"
        )
    if docs_share and not _is_expr_allowed(docs_share, share_allowed_exprs):
        errors.append(
            f"docs {alert_share} expr must match allowed contract expressions "
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
