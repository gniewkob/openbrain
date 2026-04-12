#!/usr/bin/env python3
"""Guardrail: keep selected MCP tool signatures aligned across transports."""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
MCP_TRANSPORT = ROOT / "unified/src/mcp_transport.py"
MCP_GATEWAY = ROOT / "unified/mcp-gateway/src/main.py"
CONTRACT = ROOT / "unified/contracts/tool_signature_guardrail_contract.json"


def _fail(message: str) -> int:
    print(f"[FAIL] {message}", file=sys.stderr)
    return 1


def _defaults_map(args: ast.arguments) -> dict[str, str | None]:
    values: dict[str, str | None] = {}

    positional = [*args.posonlyargs, *args.args]
    positional_defaults = [None] * (len(positional) - len(args.defaults)) + list(
        args.defaults
    )
    for arg, default in zip(positional, positional_defaults):
        values[arg.arg] = None if default is None else ast.unparse(default)

    for arg, default in zip(args.kwonlyargs, args.kw_defaults):
        values[arg.arg] = None if default is None else ast.unparse(default)

    return values


def _load_contract() -> list[str]:
    payload = json.loads(CONTRACT.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("tool_signature_guardrail_contract must be object")
    checked_tools = payload.get("checked_tools")
    if not isinstance(checked_tools, list) or not checked_tools:
        raise ValueError("contract checked_tools must be non-empty list")
    if any(not isinstance(tool, str) or not tool for tool in checked_tools):
        raise ValueError("contract checked_tools must contain non-empty strings")
    return [str(tool) for tool in checked_tools]


def _extract_signature(source: str, fn_name: str) -> list[tuple[str, str | None]]:
    tree = ast.parse(source)
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name != fn_name:
            continue
        defaults = _defaults_map(node.args)
        ordered_names: list[str] = []
        ordered_names.extend(arg.arg for arg in node.args.posonlyargs)
        ordered_names.extend(arg.arg for arg in node.args.args)
        ordered_names.extend(arg.arg for arg in node.args.kwonlyargs)
        return [(name, defaults.get(name)) for name in ordered_names]
    raise ValueError(f"{fn_name} not found")


def _check_signature_parity(
    transport_src: str, gateway_src: str, checked_tools: list[str]
) -> list[str]:
    errors: list[str] = []
    for tool in checked_tools:
        transport_sig = _extract_signature(transport_src, tool)
        gateway_sig = _extract_signature(gateway_src, tool)
        if transport_sig != gateway_sig:
            errors.append(
                f"{tool} signature drift: transport={transport_sig} gateway={gateway_sig}"
            )
    return errors


def main() -> int:
    checked_tools = _load_contract()
    transport_src = MCP_TRANSPORT.read_text(encoding="utf-8")
    gateway_src = MCP_GATEWAY.read_text(encoding="utf-8")
    errors = _check_signature_parity(transport_src, gateway_src, checked_tools)
    if errors:
        for error in errors:
            _fail(error)
        return 1
    print("Tool signature parity guardrail passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
