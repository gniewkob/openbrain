#!/usr/bin/env python3
"""Guardrail: keep brain_list filter wiring aligned across transports."""

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


def _extract_build_list_filter_keywords(source: str, fn_name: str) -> list[str]:
    tree = ast.parse(source)
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name != fn_name:
            continue
        for sub in ast.walk(node):
            if not isinstance(sub, ast.Call):
                continue
            if not isinstance(sub.func, ast.Name) or sub.func.id != "build_list_filters":
                continue
            return sorted(kw.arg for kw in sub.keywords if kw.arg is not None)
    raise ValueError(f"{fn_name} not found")


def _check_list_filter_parity(transport_src: str, gateway_src: str) -> list[str]:
    errors: list[str] = []
    transport_keywords = _extract_build_list_filter_keywords(transport_src, "brain_list")
    gateway_keywords = _extract_build_list_filter_keywords(gateway_src, "brain_list")
    if transport_keywords != gateway_keywords:
        errors.append(
            "brain_list build_list_filters keyword drift: "
            f"transport={transport_keywords} gateway={gateway_keywords}"
        )

    required = {
        "domain",
        "entity_type",
        "status",
        "sensitivity",
        "owner",
        "tenant_id",
        "include_test_data",
    }
    missing_transport = sorted(required - set(transport_keywords))
    missing_gateway = sorted(required - set(gateway_keywords))
    if missing_transport:
        errors.append(f"transport brain_list missing required filters: {missing_transport}")
    if missing_gateway:
        errors.append(f"gateway brain_list missing required filters: {missing_gateway}")
    return errors


def main() -> int:
    transport_src = MCP_TRANSPORT.read_text(encoding="utf-8")
    gateway_src = MCP_GATEWAY.read_text(encoding="utf-8")
    errors = _check_list_filter_parity(transport_src, gateway_src)
    if errors:
        for error in errors:
            _fail(error)
        return 1
    print("List filter parity guardrail passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
