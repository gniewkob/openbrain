#!/usr/bin/env python3
"""Guardrail: keep admin endpoint tool contract mapping aligned across transports."""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
MCP_TRANSPORT = ROOT / "unified/src/mcp_transport.py"
MCP_GATEWAY = ROOT / "unified/mcp-gateway/src/main.py"
CONTRACT = ROOT / "unified/contracts/admin_endpoint_guardrail_contract.json"


def _fail(message: str) -> int:
    print(f"[FAIL] {message}", file=sys.stderr)
    return 1


def _find_fn(tree: ast.Module, fn_name: str) -> ast.AsyncFunctionDef | ast.FunctionDef:
    for node in tree.body:
        if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)) and node.name == fn_name:
            return node
    raise ValueError(f"{fn_name} not found")


def _load_contract() -> list[str]:
    payload = json.loads(CONTRACT.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("admin_endpoint_guardrail_contract must be object")
    checked_tools = payload.get("checked_tools")
    if not isinstance(checked_tools, list) or not checked_tools:
        raise ValueError("contract checked_tools must be non-empty list")
    if any(not isinstance(tool, str) or not tool for tool in checked_tools):
        raise ValueError("contract checked_tools must contain non-empty strings")
    return [str(tool) for tool in checked_tools]


def _extract_dict_keys(node: ast.expr) -> tuple[str, ...]:
    if not isinstance(node, ast.Dict):
        raise ValueError("payload must be dict literal")
    keys: list[str] = []
    for key in node.keys:
        if not isinstance(key, ast.Constant) or not isinstance(key.value, str):
            raise ValueError("payload keys must be string literals")
        keys.append(key.value)
    return tuple(sorted(keys))


def _extract_path_alias(node: ast.expr) -> str:
    if not isinstance(node, ast.Call):
        raise ValueError("path argument must call memory_path helper")
    if not isinstance(node.func, ast.Name):
        raise ValueError("path helper must be a direct function call")
    if node.func.id not in {"memory_path", "memory_absolute_path"}:
        raise ValueError("path helper must be memory_path/memory_absolute_path")
    if len(node.args) != 1:
        raise ValueError("path helper must take one argument")
    first = node.args[0]
    if not isinstance(first, ast.Constant) or not isinstance(first.value, str):
        raise ValueError("path alias must be string literal")
    return first.value


def _extract_transport_call_contract(fn: ast.AsyncFunctionDef | ast.FunctionDef) -> dict[str, Any]:
    target: ast.Call | None = None
    for node in ast.walk(fn):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "_safe_req":
            target = node
            break
    if target is None:
        raise ValueError(f"{fn.name} must call _safe_req")
    if len(target.args) < 2:
        raise ValueError(f"{fn.name} _safe_req call must provide method and path")
    method_node = target.args[0]
    if not isinstance(method_node, ast.Constant) or not isinstance(method_node.value, str):
        raise ValueError(f"{fn.name} method must be string literal")
    path_alias = _extract_path_alias(target.args[1])
    payload_kind = None
    payload_keys: tuple[str, ...] = ()
    for kw in target.keywords:
        if kw.arg in {"params", "json"}:
            payload_kind = kw.arg
            payload_keys = _extract_dict_keys(kw.value)
            break
    return {
        "method": method_node.value,
        "path_alias": path_alias,
        "payload_kind": payload_kind,
        "payload_keys": payload_keys,
    }


def _extract_gateway_call_contract(fn: ast.AsyncFunctionDef | ast.FunctionDef) -> dict[str, Any]:
    target: ast.Call | None = None
    for node in ast.walk(fn):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "_request_or_raise"
        ):
            target = node
            break
    if target is None:
        raise ValueError(f"{fn.name} must call _request_or_raise")
    if len(target.args) < 3:
        raise ValueError(f"{fn.name} _request_or_raise call must provide client/method/path")
    method_node = target.args[1]
    if not isinstance(method_node, ast.Constant) or not isinstance(method_node.value, str):
        raise ValueError(f"{fn.name} method must be string literal")
    path_alias = _extract_path_alias(target.args[2])
    payload_kind = None
    payload_keys: tuple[str, ...] = ()
    for kw in target.keywords:
        if kw.arg in {"params", "json"}:
            payload_kind = kw.arg
            payload_keys = _extract_dict_keys(kw.value)
            break
    return {
        "method": method_node.value,
        "path_alias": path_alias,
        "payload_kind": payload_kind,
        "payload_keys": payload_keys,
    }


def _extract_contracts(
    source: str, *, transport: bool, checked_tools: list[str]
) -> dict[str, dict[str, Any]]:
    tree = ast.parse(source)
    contracts: dict[str, dict[str, Any]] = {}
    for fn_name in checked_tools:
        fn = _find_fn(tree, fn_name)
        contracts[fn_name] = (
            _extract_transport_call_contract(fn)
            if transport
            else _extract_gateway_call_contract(fn)
        )
    return contracts


def _check_admin_endpoint_contract_parity(
    transport_source: str, gateway_source: str, checked_tools: list[str]
) -> list[str]:
    transport_contracts = _extract_contracts(
        transport_source, transport=True, checked_tools=checked_tools
    )
    gateway_contracts = _extract_contracts(
        gateway_source, transport=False, checked_tools=checked_tools
    )
    errors: list[str] = []
    for fn_name in checked_tools:
        if transport_contracts[fn_name] != gateway_contracts[fn_name]:
            errors.append(
                f"{fn_name} endpoint contract drift: transport={transport_contracts[fn_name]} gateway={gateway_contracts[fn_name]}"
            )
    return errors


def main() -> int:
    checked_tools = _load_contract()
    transport_source = MCP_TRANSPORT.read_text(encoding="utf-8")
    gateway_source = MCP_GATEWAY.read_text(encoding="utf-8")
    errors = _check_admin_endpoint_contract_parity(
        transport_source, gateway_source, checked_tools
    )
    if errors:
        for error in errors:
            _fail(error)
        return 1
    print("Admin endpoint contract parity guardrail passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
