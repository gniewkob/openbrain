#!/usr/bin/env python3
"""Guardrail: enforce capabilities tier status parity across transports."""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
CONTRACT = ROOT / "unified/contracts/capabilities_response_contract.json"
HTTP_TRANSPORT = ROOT / "unified/src/mcp_transport.py"
STDIO_GATEWAY = ROOT / "unified/mcp-gateway/src/main.py"
TIER_KEYS = ("tier_1_core", "tier_2_advanced", "tier_3_admin")


def _fail(message: str) -> int:
    print(f"[FAIL] {message}", file=sys.stderr)
    return 1


def _find_async_function(tree: ast.Module, name: str) -> ast.AsyncFunctionDef:
    for node in tree.body:
        if isinstance(node, ast.AsyncFunctionDef) and node.name == name:
            return node
    raise ValueError(f"{name} not found")


def _extract_tier_statuses(source: str) -> dict[str, str]:
    tree = ast.parse(source)
    fn = _find_async_function(tree, "brain_capabilities")
    for node in ast.walk(fn):
        if not isinstance(node, ast.Return) or not isinstance(node.value, ast.Dict):
            continue
        result: dict[str, str] = {}
        for key_node, value_node in zip(node.value.keys, node.value.values):
            if not isinstance(key_node, ast.Constant) or not isinstance(key_node.value, str):
                continue
            key = key_node.value
            if key not in TIER_KEYS:
                continue
            if not isinstance(value_node, ast.Dict):
                raise ValueError(f"{key} payload must be dict")
            status_value: str | None = None
            for tier_key_node, tier_value_node in zip(value_node.keys, value_node.values):
                if (
                    isinstance(tier_key_node, ast.Constant)
                    and tier_key_node.value == "status"
                    and isinstance(tier_value_node, ast.Constant)
                    and isinstance(tier_value_node.value, str)
                ):
                    status_value = tier_value_node.value
                    break
            if status_value is None:
                raise ValueError(f"{key} must define string status")
            result[key] = status_value
        if result:
            return result
    raise ValueError("brain_capabilities return payload not found")


def _check_tier_status_parity(
    transport_source: str,
    gateway_source: str,
    allowed_values: set[str],
) -> list[str]:
    transport_statuses = _extract_tier_statuses(transport_source)
    gateway_statuses = _extract_tier_statuses(gateway_source)
    errors: list[str] = []

    for label, statuses in (("transport", transport_statuses), ("gateway", gateway_statuses)):
        missing = [tier for tier in TIER_KEYS if tier not in statuses]
        if missing:
            errors.append(f"{label} missing tier statuses for {missing}")
            continue
        bad = [f"{tier}={statuses[tier]!r}" for tier in TIER_KEYS if statuses[tier] not in allowed_values]
        if bad:
            errors.append(
                f"{label} tier status values must be in {sorted(allowed_values)}; got {bad}"
            )

    if transport_statuses != gateway_statuses:
        errors.append(
            f"tier status drift: transport={transport_statuses} gateway={gateway_statuses}"
        )
    return errors


def main() -> int:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    allowed_values = set(contract.get("tier_status_values", []))
    if not allowed_values:
        _fail("contract tier_status_values must be non-empty")
        return 1

    transport_source = HTTP_TRANSPORT.read_text(encoding="utf-8")
    gateway_source = STDIO_GATEWAY.read_text(encoding="utf-8")
    errors = _check_tier_status_parity(transport_source, gateway_source, allowed_values)
    if errors:
        for error in errors:
            _fail(error)
        return 1
    print("Capabilities tier status parity guardrail passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
