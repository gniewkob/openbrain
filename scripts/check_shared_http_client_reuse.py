#!/usr/bin/env python3
"""Guardrail: ensure both transports keep shared AsyncClient reuse semantics."""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
MCP_TRANSPORT = ROOT / "unified/src/mcp_transport.py"
MCP_GATEWAY = ROOT / "unified/mcp-gateway/src/main.py"
CONTRACT = ROOT / "unified/contracts/shared_http_client_reuse_contract.json"


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


def _load_contract() -> dict[str, object]:
    payload = json.loads(CONTRACT.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("shared_http_client_reuse_contract must be object")
    required_globals = payload.get("required_globals")
    required_refresh_snippets = payload.get("required_refresh_snippets")
    if (
        not isinstance(required_globals, list)
        or not required_globals
        or any(not isinstance(v, str) or not v for v in required_globals)
    ):
        raise ValueError("contract required_globals must be non-empty list[str]")
    if (
        not isinstance(required_refresh_snippets, list)
        or not required_refresh_snippets
        or any(not isinstance(v, str) or not v for v in required_refresh_snippets)
    ):
        raise ValueError("contract required_refresh_snippets must be non-empty list[str]")
    for key in (
        "required_client_factory_name",
        "required_client_factory_return_call",
        "required_shared_client_class_name",
    ):
        value = payload.get(key)
        if not isinstance(value, str) or not value:
            raise ValueError(f"contract {key} must be non-empty string")
    return payload


def _has_annotated_global(tree: ast.AST, name: str) -> bool:
    for node in ast.walk(tree):
        if not isinstance(node, ast.AnnAssign):
            continue
        if isinstance(node.target, ast.Name) and node.target.id == name:
            return True
    return False


def _returns_named_instance(
    fn: ast.FunctionDef | ast.AsyncFunctionDef, expected_ctor: str
) -> bool:
    for node in ast.walk(fn):
        if not isinstance(node, ast.Return):
            continue
        if isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name):
            if node.value.func.id == expected_ctor:
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


def _has_client_config_refresh_path(source: str, required_snippets: list[str]) -> bool:
    return all(snippet in source for snippet in required_snippets)


def _check_source(source: str, label: str, contract: dict[str, object]) -> list[str]:
    tree = ast.parse(source)
    errors: list[str] = []
    required_globals = [str(item) for item in contract["required_globals"]]
    required_refresh_snippets = [
        str(item) for item in contract["required_refresh_snippets"]
    ]
    client_factory_name = str(contract["required_client_factory_name"])
    client_factory_ctor = str(contract["required_client_factory_return_call"])
    shared_class_name = str(contract["required_shared_client_class_name"])

    for global_name in required_globals:
        if not _has_annotated_global(tree, global_name):
            errors.append(f"{label} must define module-level {global_name}")
    if not _has_client_config_refresh_path(source, required_refresh_snippets):
        errors.append(
            f"{label} must include client refresh path for runtime config drift"
        )

    client_fn = _find_function(tree, client_factory_name)
    if not _returns_named_instance(client_fn, client_factory_ctor):
        errors.append(
            f"{label} {client_factory_name}() must return {client_factory_ctor}()"
        )

    shared_client = _find_class(tree, shared_class_name)
    if not _class_has_async_enter_with_asyncclient(shared_client):
        errors.append(
            f"{label} {shared_class_name}.__aenter__ must guard _http_client is None and build httpx.AsyncClient"
        )
    return errors


def main() -> int:
    contract = _load_contract()
    transport_src = MCP_TRANSPORT.read_text(encoding="utf-8")
    gateway_src = MCP_GATEWAY.read_text(encoding="utf-8")

    errors: list[str] = []
    errors.extend(_check_source(transport_src, "HTTP transport", contract))
    errors.extend(_check_source(gateway_src, "stdio gateway", contract))

    if errors:
        for error in errors:
            _fail(error)
        return 1
    print("Shared HTTP client reuse guardrail passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
