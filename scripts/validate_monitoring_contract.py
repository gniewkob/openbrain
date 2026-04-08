#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from pathlib import Path

PROMQL_RESERVED_WORDS = {
    "sum",
    "rate",
    "increase",
    "clamp_min",
    "histogram_quantile",
    "max",
    "min",
    "avg",
    "by",
    "without",
    "on",
    "ignoring",
    "group_left",
    "group_right",
    "or",
    "and",
    "unless",
    "bool",
    "vector",
    "time",
}

PROMQL_LABELS_TO_IGNORE = {"le", "job", "component", "status", "domain", "instance"}
PROMQL_SYMBOL_RE = re.compile(r"\b[a-zA-Z_:][a-zA-Z0-9_:]*\b")
METRIC_TYPE_RE = re.compile(r"^# TYPE\s+([a-zA-Z_:][a-zA-Z0-9_:]*)\s+")
QUOTED_STRING_RE = re.compile(r'"[^"]*"')


def load_contract(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_dashboard_exprs(path: Path) -> list[tuple[str, str]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    out: list[tuple[str, str]] = []
    for panel in payload.get("panels", []):
        title = panel.get("title", "<untitled>")
        for target in panel.get("targets", []):
            expr = target.get("expr")
            if expr:
                out.append((title, expr))
    return out


def extract_metric_tokens(expr: str) -> set[str]:
    expr_wo_strings = QUOTED_STRING_RE.sub("", expr)
    symbols = set(PROMQL_SYMBOL_RE.findall(expr_wo_strings))
    result: set[str] = set()
    for symbol in symbols:
        if symbol in PROMQL_RESERVED_WORDS:
            continue
        if symbol in PROMQL_LABELS_TO_IGNORE:
            continue
        if symbol.startswith("refId"):
            continue
        if symbol.isupper():
            continue
        result.add(symbol)
    return result


def metric_is_allowed(metric: str, allowed: set[str]) -> bool:
    if metric in allowed:
        return True
    for suffix in ("_bucket", "_sum", "_count"):
        if metric.endswith(suffix):
            base = metric[: -len(suffix)]
            if base in allowed:
                return True
    return False


def fetch_metric_names(url: str) -> set[str]:
    text = urllib.request.urlopen(url, timeout=5).read().decode("utf-8", errors="replace")
    names: set[str] = set()
    for line in text.splitlines():
        match = METRIC_TYPE_RE.match(line)
        if match:
            names.add(match.group(1))
    return names


def validate_monitoring_contract(
    contract: dict,
    dashboard_paths: list[Path],
    *,
    forbid_vector_zero: bool,
    check_live_metrics: bool,
    metrics_url: str,
) -> tuple[list[str], set[str], set[str]]:
    errors: list[str] = []
    required_metrics = set(contract.get("required_metrics", []))
    referenced_metrics: set[str] = set()

    for dashboard_path in dashboard_paths:
        if not dashboard_path.exists():
            errors.append(f"Missing dashboard file: {dashboard_path}")
            continue
        for title, expr in load_dashboard_exprs(dashboard_path):
            if forbid_vector_zero and "vector(0)" in expr:
                errors.append(f"Forbidden vector(0) in panel '{title}': {expr}")
            referenced_metrics |= extract_metric_tokens(expr)

    unexpected = sorted(m for m in referenced_metrics if not metric_is_allowed(m, required_metrics))
    if unexpected:
        errors.append("Dashboard references metrics not in contract: " + ", ".join(unexpected))

    live_metrics: set[str] = set()
    if check_live_metrics:
        try:
            live_metrics = fetch_metric_names(metrics_url)
        except Exception as exc:  # pragma: no cover - guarded by tests via monkeypatch
            errors.append(f"Failed to fetch live metrics from {metrics_url}: {exc}")
        else:
            missing_live = sorted(m for m in required_metrics if m not in live_metrics and m != "up")
            if missing_live:
                errors.append("Required metrics missing in live /metrics: " + ", ".join(missing_live))

    return errors, referenced_metrics, live_metrics


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate OpenBrain monitoring contract")
    parser.add_argument("--contract", default="monitoring/contracts/openbrain-metrics-contract.json")
    parser.add_argument("--metrics-url", default="http://127.0.0.1:9180/metrics")
    parser.add_argument("--check-live", action="store_true", help="Validate contract against live /metrics")
    parser.add_argument(
        "--allow-vector-zero",
        action="store_true",
        help="Allow vector(0) usage in dashboard expressions (default: forbidden).",
    )
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    contract_path = (root / args.contract).resolve()
    contract = load_contract(contract_path)
    dashboard_paths = [root / rel for rel in contract.get("dashboard_files", [])]

    errors, referenced_metrics, live_metrics = validate_monitoring_contract(
        contract,
        dashboard_paths,
        forbid_vector_zero=not args.allow_vector_zero,
        check_live_metrics=args.check_live,
        metrics_url=args.metrics_url,
    )

    if errors:
        print("MONITORING CONTRACT CHECK: FAILED")
        for error in errors:
            print(f"- {error}")
        return 1

    print("MONITORING CONTRACT CHECK: OK")
    print(f"- required metrics: {len(contract.get('required_metrics', []))}")
    print(f"- referenced dashboard metrics: {len(referenced_metrics)}")
    if args.check_live:
        print(f"- live /metrics names: {len(live_metrics)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
