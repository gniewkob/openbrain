#!/usr/bin/env python3
"""Guardrail: keep selected MCP tool signatures aligned across transports."""

from __future__ import annotations

import ast
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
MCP_TRANSPORT = ROOT / "unified/src/mcp_transport.py"
MCP_GATEWAY = ROOT / "unified/mcp-gateway/src/main.py"

CHECKED_TOOLS = (
    "brain_search",
    "brain_list",
    "brain_delete",
    "brain_update",
)


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


def _check_signature_parity(transport_src: str, gateway_src: str) -> list[str]:
    errors: list[str] = []
    for tool in CHECKED_TOOLS:
        transport_sig = _extract_signature(transport_src, tool)
        gateway_sig = _extract_signature(gateway_src, tool)
        if transport_sig != gateway_sig:
            errors.append(
                f"{tool} signature drift: transport={transport_sig} gateway={gateway_sig}"
            )
    return errors


def main() -> int:
    transport_src = MCP_TRANSPORT.read_text(encoding="utf-8")
    gateway_src = MCP_GATEWAY.read_text(encoding="utf-8")
    errors = _check_signature_parity(transport_src, gateway_src)
    if errors:
        for error in errors:
            _fail(error)
        return 1
    print("Tool signature parity guardrail passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
