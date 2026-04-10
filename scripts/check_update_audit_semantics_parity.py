#!/usr/bin/env python3
"""Guardrail: keep brain_update audit semantics aligned across transports."""

from __future__ import annotations

import ast
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
MCP_TRANSPORT = ROOT / "unified/src/mcp_transport.py"
MCP_GATEWAY = ROOT / "unified/mcp-gateway/src/main.py"


def _fail(message: str) -> int:
    print(f"[FAIL] {message}", file=sys.stderr)
    return 1


def _find_function(source: str, fn_name: str) -> ast.FunctionDef | ast.AsyncFunctionDef:
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == fn_name:
            return node
    raise ValueError(f"{fn_name} not found")


def _has_normalize_updated_by_call(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    for node in ast.walk(fn):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Name) or node.func.id != "normalize_updated_by":
            continue
        if not node.args:
            continue
        arg = node.args[0]
        if isinstance(arg, ast.Name) and arg.id == "updated_by":
            return True
    return False


def _dict_has_canonical_updated_by(node: ast.Dict) -> bool:
    for key, value in zip(node.keys, node.values):
        if not isinstance(key, ast.Constant) or key.value != "updated_by":
            continue
        if not isinstance(value, ast.Call):
            continue
        if isinstance(value.func, ast.Name) and value.func.id == "canonical_updated_by":
            return True
    return False


def _has_payload_canonical_updated_by(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    for node in ast.walk(fn):
        if isinstance(node, ast.Dict) and _dict_has_canonical_updated_by(node):
            return True
    return False


def _check_update_semantics(source: str, label: str) -> list[str]:
    errors: list[str] = []
    fn = _find_function(source, "brain_update")
    if not _has_normalize_updated_by_call(fn):
        errors.append(f"{label} brain_update must call normalize_updated_by(updated_by)")
    if not _has_payload_canonical_updated_by(fn):
        errors.append(
            f"{label} brain_update must send updated_by=canonical_updated_by() in PATCH payload"
        )
    return errors


def main() -> int:
    transport_src = MCP_TRANSPORT.read_text(encoding="utf-8")
    gateway_src = MCP_GATEWAY.read_text(encoding="utf-8")
    errors: list[str] = []
    errors.extend(_check_update_semantics(transport_src, "HTTP transport"))
    errors.extend(_check_update_semantics(gateway_src, "stdio gateway"))
    if errors:
        for error in errors:
            _fail(error)
        return 1
    print("Update audit semantics parity guardrail passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
