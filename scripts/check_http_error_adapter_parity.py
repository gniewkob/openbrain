#!/usr/bin/env python3
"""Guardrail: keep HTTP error adapter semantics aligned across transports."""

from __future__ import annotations

import ast
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
MCP_TRANSPORT = ROOT / "unified/src/http_error_adapter.py"
MCP_GATEWAY = ROOT / "unified/mcp-gateway/src/http_error_adapter.py"

REQUIRED_DEFAULT_KEYS = {"status_labels", "fallback_5xx", "fallback_other", "detail_hints"}


def _fail(message: str) -> int:
    print(f"[FAIL] {message}", file=sys.stderr)
    return 1


def _find_function(tree: ast.AST, fn_name: str) -> ast.FunctionDef:
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == fn_name:
            return node
    raise ValueError(f"{fn_name} not found")


def _extract_default_keys(tree: ast.AST) -> set[str]:
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(target, ast.Name) and target.id == "_DEFAULTS" for target in node.targets):
            continue
        if not isinstance(node.value, ast.Dict):
            continue
        keys: set[str] = set()
        for key in node.value.keys:
            if isinstance(key, ast.Constant) and isinstance(key.value, str):
                keys.add(key.value)
        return keys
    raise ValueError("_DEFAULTS assignment not found")


def _check_backend_error_message_semantics(fn: ast.FunctionDef, label: str) -> list[str]:
    errors: list[str] = []
    calls = [node for node in ast.walk(fn) if isinstance(node, ast.Call)]
    name_calls = {call.func.id for call in calls if isinstance(call.func, ast.Name)}
    attr_calls = [
        call.func
        for call in calls
        if isinstance(call.func, ast.Attribute) and isinstance(call.func.value, ast.Name)
    ]

    has_json_dumps = any(
        attr.value.id == "json" and attr.attr == "dumps" for attr in attr_calls
    )
    if not has_json_dumps:
        errors.append(f"{label} backend_error_message must use json.dumps for dict/list details")

    if "str" not in name_calls:
        errors.append(f"{label} backend_error_message must normalize non-JSON detail via str()")

    contains_detail_hints = any(
        isinstance(node, ast.Constant) and node.value == "detail_hints"
        for node in ast.walk(fn)
    )
    if not contains_detail_hints:
        errors.append(f"{label} backend_error_message must consult contract detail_hints")

    contains_fallback_other = any(
        isinstance(node, ast.Constant) and node.value == "fallback_other"
        for node in ast.walk(fn)
    )
    if not contains_fallback_other:
        errors.append(f"{label} backend_error_message must use fallback_other contract label")

    has_backend_prefix = any(
        isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and node.value.startswith("Backend ")
        for node in ast.walk(fn)
    )
    if not has_backend_prefix:
        errors.append(f"{label} backend_error_message must return Backend <status> prefix")
    return errors


def _check_backend_request_failure_semantics(fn: ast.FunctionDef, label: str) -> list[str]:
    text_constants = {
        node.value
        for node in ast.walk(fn)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    expected_prod = "Backend request failed: upstream unavailable"
    if expected_prod not in text_constants:
        return [f"{label} backend_request_failure_message must keep production-safe fallback"]
    return []


def _check_source(source: str, label: str) -> list[str]:
    tree = ast.parse(source)
    errors: list[str] = []
    default_keys = _extract_default_keys(tree)
    if default_keys != REQUIRED_DEFAULT_KEYS:
        errors.append(
            f"{label} _DEFAULTS keys drift: expected={sorted(REQUIRED_DEFAULT_KEYS)} got={sorted(default_keys)}"
        )
    errors.extend(
        _check_backend_error_message_semantics(_find_function(tree, "backend_error_message"), label)
    )
    errors.extend(
        _check_backend_request_failure_semantics(
            _find_function(tree, "backend_request_failure_message"), label
        )
    )
    return errors


def main() -> int:
    transport_src = MCP_TRANSPORT.read_text(encoding="utf-8")
    gateway_src = MCP_GATEWAY.read_text(encoding="utf-8")
    errors: list[str] = []
    errors.extend(_check_source(transport_src, "HTTP transport"))
    errors.extend(_check_source(gateway_src, "stdio gateway"))
    if errors:
        for error in errors:
            _fail(error)
        return 1
    print("HTTP error adapter parity guardrail passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
