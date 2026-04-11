#!/usr/bin/env python3
"""Guardrail: ensure capabilities health logic stays in parity across transports."""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
HTTP_HEALTH = ROOT / "unified/src/capabilities_health.py"
GATEWAY_HEALTH = ROOT / "unified/mcp-gateway/src/capabilities_health.py"
CONTRACT = ROOT / "unified/contracts/capabilities_health_guardrail_contract.json"


def _fail(message: str) -> int:
    print(f"[FAIL] {message}", file=sys.stderr)
    return 1


def _extract_function_ast(tree: ast.AST, fn_name: str) -> str:
    for node in getattr(tree, "body", []):
        if isinstance(node, ast.FunctionDef) and node.name == fn_name:
            return ast.dump(node, include_attributes=False)
    raise ValueError(f"{fn_name} not found")


def _load_contract() -> dict[str, object]:
    payload = json.loads(CONTRACT.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("capabilities_health_guardrail_contract must be object")
    fn_names = payload.get("required_function_names")
    if not isinstance(fn_names, list) or not fn_names:
        raise ValueError("contract required_function_names must be non-empty list")
    if any(not isinstance(name, str) or not name for name in fn_names):
        raise ValueError("contract required_function_names must contain non-empty strings")
    return payload


def _check_health_parity(
    http_src: str, gateway_src: str, required_function_names: list[str]
) -> list[str]:
    errors: list[str] = []
    http_tree = ast.parse(http_src)
    gateway_tree = ast.parse(gateway_src)

    for fn_name in required_function_names:
        if _extract_function_ast(http_tree, fn_name) != _extract_function_ast(
            gateway_tree,
            fn_name,
        ):
            errors.append(
                f"{fn_name} logic must stay identical in HTTP and gateway health modules"
            )
    return errors


def main() -> int:
    contract = _load_contract()
    required_function_names = [str(name) for name in contract["required_function_names"]]
    http_src = HTTP_HEALTH.read_text(encoding="utf-8")
    gateway_src = GATEWAY_HEALTH.read_text(encoding="utf-8")
    errors = _check_health_parity(http_src, gateway_src, required_function_names)
    if errors:
        for err in errors:
            _fail(err)
        return 1
    print("Capabilities health parity guardrail passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
