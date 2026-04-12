#!/usr/bin/env python3
"""Guardrail: ensure telemetry gauge names are declared in monitoring contract."""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
TELEMETRY_GAUGES = ROOT / "unified/src/telemetry_gauges.py"
MONITORING_CONTRACT = ROOT / "monitoring/contracts/openbrain-metrics-contract.json"


def _fail(message: str) -> int:
    print(f"[FAIL] {message}", file=sys.stderr)
    return 1


def _collect_string_keys(dict_node: ast.Dict) -> set[str]:
    keys: set[str] = set()
    for key in dict_node.keys:
        if isinstance(key, ast.Constant) and isinstance(key.value, str):
            keys.add(key.value)
    return keys


def _collect_gauge_names_from_source(source: str) -> set[str]:
    tree = ast.parse(source)
    gauge_names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        gauge_names |= _collect_string_keys(node)
    return {name for name in gauge_names if name.endswith("_total")}


def _collect_required_metrics(contract_payload: dict[str, object]) -> set[str]:
    required = contract_payload.get("required_metrics")
    if not isinstance(required, list):
        raise ValueError("monitoring contract required_metrics must be a list")
    names: set[str] = set()
    for item in required:
        if isinstance(item, str):
            names.add(item)
    return names


def main() -> int:
    telemetry_source = TELEMETRY_GAUGES.read_text(encoding="utf-8")
    contract_payload = json.loads(MONITORING_CONTRACT.read_text(encoding="utf-8"))

    gauge_names = _collect_gauge_names_from_source(telemetry_source)
    required_metrics = _collect_required_metrics(contract_payload)
    missing = sorted(name for name in gauge_names if name not in required_metrics)
    if missing:
        _fail(
            "monitoring contract missing telemetry gauge metrics: " + ", ".join(missing)
        )
        return 1
    print("Telemetry contract parity guardrail passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
