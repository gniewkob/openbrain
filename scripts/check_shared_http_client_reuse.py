#!/usr/bin/env python3
"""Guardrail: ensure both transports keep shared AsyncClient reuse semantics."""

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


def _find_class(tree: ast.AST, name: str) -> ast.ClassDef:
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == name:
            return node
    raise ValueError(f"class {name} not found")


def _find_function(tree: ast.AST, name: str) -> ast.FunctionDef | ast.AsyncFunctionDef:
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise ValueError(f"function {name} not found")


def _has_http_client_global(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if not isinstance(node, ast.AnnAssign):
            continue
        if isinstance(node.target, ast.Name) and node.target.id == "_http_client":
            return True
    return False


def _has_http_client_config_key_global(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if not isinstance(node, ast.AnnAssign):
            continue
        if (
            isinstance(node.target, ast.Name)
            and node.target.id == "_http_client_config_key"
        ):
            return True
    return False


def _returns_shared_client_instance(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    for node in ast.walk(fn):
        if not isinstance(node, ast.Return):
            continue
        if isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name):
            if node.value.func.id == "_SharedClient":
                return True
    return False


def _class_has_async_enter_with_asyncclient(klass: ast.ClassDef) -> bool:
    for node in klass.body:
        if not isinstance(node, ast.AsyncFunctionDef) or node.name != "__aenter__":
            continue
        has_none_guard = any(
            isinstance(sub, ast.Compare)
            and isinstance(sub.left, ast.Name)
            and sub.left.id == "_http_client"
            and any(isinstance(op, ast.Is) for op in sub.ops)
            and any(isinstance(comp, ast.Constant) and comp.value is None for comp in sub.comparators)
            for sub in ast.walk(node)
        )
        has_asyncclient_ctor = any(
            isinstance(sub, ast.Call)
            and isinstance(sub.func, ast.Attribute)
            and isinstance(sub.func.value, ast.Name)
            and sub.func.value.id == "httpx"
            and sub.func.attr == "AsyncClient"
            for sub in ast.walk(node)
        )
        if has_none_guard and has_asyncclient_ctor:
            return True
    return False


def _has_client_config_refresh_path(source: str) -> bool:
    required_snippets = (
        "_current_http_client_config_key",
        "_http_client_config_key",
        "mcp_client_refreshed_due_to_config_drift",
    )
    return all(snippet in source for snippet in required_snippets)


def _check_source(source: str, label: str) -> list[str]:
    tree = ast.parse(source)
    errors: list[str] = []
    if not _has_http_client_global(tree):
        errors.append(f"{label} must define module-level _http_client")
    if not _has_http_client_config_key_global(tree):
        errors.append(f"{label} must define module-level _http_client_config_key")
    if not _has_client_config_refresh_path(source):
        errors.append(
            f"{label} must include client refresh path for runtime config drift"
        )

    client_fn = _find_function(tree, "_client")
    if not _returns_shared_client_instance(client_fn):
        errors.append(f"{label} _client() must return _SharedClient()")

    shared_client = _find_class(tree, "_SharedClient")
    if not _class_has_async_enter_with_asyncclient(shared_client):
        errors.append(
            f"{label} _SharedClient.__aenter__ must guard _http_client is None and build httpx.AsyncClient"
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
    print("Shared HTTP client reuse guardrail passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
