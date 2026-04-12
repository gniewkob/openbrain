#!/usr/bin/env python3
"""Guardrail: keep admin tool parameter bounds aligned across transports."""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
MCP_TRANSPORT = ROOT / "unified/src/mcp_transport.py"
MCP_GATEWAY = ROOT / "unified/mcp-gateway/src/main.py"
CONTRACT = ROOT / "unified/contracts/admin_bounds_guardrail_contract.json"


def _fail(message: str) -> int:
    print(f"[FAIL] {message}", file=sys.stderr)
    return 1


def _extract_function(tree: ast.Module, fn_name: str) -> ast.AsyncFunctionDef | ast.FunctionDef:
    for node in tree.body:
        if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)) and node.name == fn_name:
            return node
    raise ValueError(f"{fn_name} not found")


def _load_contract() -> list[tuple[str, str]]:
    payload = json.loads(CONTRACT.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("admin_bounds_guardrail_contract must be object")
    checked = payload.get("checked_bounds")
    if not isinstance(checked, list) or not checked:
        raise ValueError("contract checked_bounds must be non-empty list")

    result: list[tuple[str, str]] = []
    for item in checked:
        if not isinstance(item, dict):
            raise ValueError("contract checked_bounds entries must be objects")
        fn_name = item.get("function")
        param = item.get("parameter")
        if not isinstance(fn_name, str) or not fn_name:
            raise ValueError("contract checked_bounds.function must be non-empty string")
        if not isinstance(param, str) or not param:
            raise ValueError("contract checked_bounds.parameter must be non-empty string")
        result.append((fn_name, param))
    return result


def _extract_param_default(fn: ast.AsyncFunctionDef | ast.FunctionDef, param: str) -> int | None:
    positional = [*fn.args.posonlyargs, *fn.args.args]
    defaults = [None] * (len(positional) - len(fn.args.defaults)) + list(fn.args.defaults)
    for arg, default in zip(positional, defaults):
        if arg.arg != param:
            continue
        if isinstance(default, ast.Constant) and isinstance(default.value, int):
            return int(default.value)
        if default is None:
            return None
        raise ValueError(f"{fn.name}.{param} default is not an integer literal")
    raise ValueError(f"{fn.name}.{param} parameter not found")


def _extract_bounds(
    fn: ast.AsyncFunctionDef | ast.FunctionDef,
    param: str,
) -> tuple[int, int]:
    for node in fn.body:
        if not isinstance(node, ast.If) or not isinstance(node.test, ast.UnaryOp):
            continue
        if not isinstance(node.test.op, ast.Not):
            continue
        compare = node.test.operand
        if not isinstance(compare, ast.Compare):
            continue
        if not isinstance(compare.left, ast.Constant) or not isinstance(compare.left.value, int):
            continue
        if len(compare.ops) != 2 or len(compare.comparators) != 2:
            continue
        if not isinstance(compare.ops[0], ast.LtE) or not isinstance(compare.ops[1], ast.LtE):
            continue
        first = compare.comparators[0]
        second = compare.comparators[1]
        if not isinstance(first, ast.Name) or first.id != param:
            continue
        if not isinstance(second, ast.Constant) or not isinstance(second.value, int):
            continue
        return int(compare.left.value), int(second.value)
    raise ValueError(f"{fn.name}.{param} bounds check not found")


def _extract_contract(
    source: str,
    fn_name: str,
    param: str,
) -> tuple[int, int, int | None]:
    tree = ast.parse(source)
    fn = _extract_function(tree, fn_name)
    low, high = _extract_bounds(fn, param)
    default = _extract_param_default(fn, param)
    return low, high, default


def _check_admin_bounds_parity(
    transport_src: str, gateway_src: str, checked_bounds: list[tuple[str, str]]
) -> list[str]:
    errors: list[str] = []
    for fn_name, param in checked_bounds:
        transport_contract = _extract_contract(transport_src, fn_name, param)
        gateway_contract = _extract_contract(gateway_src, fn_name, param)
        if transport_contract != gateway_contract:
            errors.append(
                f"{fn_name}.{param} drift: transport={transport_contract} gateway={gateway_contract}"
            )
    return errors


def main() -> int:
    checked_bounds = _load_contract()
    transport_src = MCP_TRANSPORT.read_text(encoding="utf-8")
    gateway_src = MCP_GATEWAY.read_text(encoding="utf-8")
    errors = _check_admin_bounds_parity(transport_src, gateway_src, checked_bounds)
    if errors:
        for error in errors:
            _fail(error)
        return 1
    print("Admin bounds parity guardrail passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
