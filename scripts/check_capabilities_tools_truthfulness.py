#!/usr/bin/env python3
"""Guardrail: ensure capabilities tool lists map to real MCP tool functions."""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "unified/contracts/capabilities_manifest.json"
HTTP_TRANSPORT = ROOT / "unified/src/mcp_transport.py"
STDIO_GATEWAY = ROOT / "unified/mcp-gateway/src/main.py"


def _fail(message: str) -> int:
    print(f"[FAIL] {message}", file=sys.stderr)
    return 1


def _is_mcp_tool_decorator(node: ast.expr) -> bool:
    if isinstance(node, ast.Call):
        node = node.func
    return (
        isinstance(node, ast.Attribute)
        and node.attr == "tool"
        and isinstance(node.value, ast.Name)
        and node.value.id == "mcp"
    )


def _collect_tool_functions(source: str) -> dict[str, bool]:
    tree = ast.parse(source)
    tools: dict[str, bool] = {}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        tools[node.name] = any(_is_mcp_tool_decorator(d) for d in node.decorator_list)
    return tools


def _expected_tool_names(tool_suffixes: list[str]) -> set[str]:
    return {f"brain_{name}" for name in tool_suffixes}


def _check_expected_tools(
    available: dict[str, bool],
    expected: set[str],
    label: str,
) -> list[str]:
    errors: list[str] = []
    missing = sorted(name for name in expected if name not in available)
    if missing:
        errors.append(f"{label} missing tool functions: {missing}")

    undecorated = sorted(
        name for name in expected if name in available and not available[name]
    )
    if undecorated:
        errors.append(f"{label} expected @mcp.tool decorators on: {undecorated}")
    return errors


def _check_manifest_coverage(
    source: str,
    manifest: dict[str, list[str]],
    *,
    label: str,
    obsidian_key: str,
) -> list[str]:
    available = _collect_tool_functions(source)
    expected = _expected_tool_names(
        [
            *manifest["core_tools"],
            *manifest["advanced_tools"],
            *manifest["admin_tools"],
            *manifest[obsidian_key],
        ]
    )
    return _check_expected_tools(available, expected, label)


def main() -> int:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    transport_src = HTTP_TRANSPORT.read_text(encoding="utf-8")
    gateway_src = STDIO_GATEWAY.read_text(encoding="utf-8")

    errors: list[str] = []
    errors.extend(
        _check_manifest_coverage(
            transport_src,
            manifest,
            label="HTTP transport",
            obsidian_key="http_obsidian_tools",
        )
    )
    errors.extend(
        _check_manifest_coverage(
            gateway_src,
            manifest,
            label="stdio gateway",
            obsidian_key="local_obsidian_tools",
        )
    )
    if errors:
        for error in errors:
            _fail(error)
        return 1
    print("Capabilities tools truthfulness guardrail passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
