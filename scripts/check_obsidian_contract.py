#!/usr/bin/env python3
"""Guardrail: enforce Obsidian tool gating and capabilities contract invariants."""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "unified/contracts/capabilities_manifest.json"
GATEWAY_MAIN = ROOT / "unified/mcp-gateway/src/main.py"
HTTP_TRANSPORT = ROOT / "unified/src/mcp_transport.py"


def _fail(message: str) -> int:
    print(f"[FAIL] {message}", file=sys.stderr)
    return 1


def _check_manifest() -> list[str]:
    errors: list[str] = []
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    http_tools = payload.get("http_obsidian_tools", [])
    local_tools = payload.get("local_obsidian_tools", [])
    if not isinstance(http_tools, list) or not http_tools:
        errors.append("capabilities_manifest http_obsidian_tools must be a non-empty list")
    if not isinstance(local_tools, list) or not local_tools:
        errors.append("capabilities_manifest local_obsidian_tools must be a non-empty list")
    missing = [tool for tool in http_tools if tool not in local_tools]
    if missing:
        errors.append(f"http_obsidian_tools must be subset of local_obsidian_tools: missing={missing}")
    return errors


def _find_async_function(tree: ast.AST, function_name: str) -> ast.AsyncFunctionDef | None:
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == function_name:
            return node
    return None


def _function_calls_name(func: ast.AsyncFunctionDef, call_name: str) -> bool:
    for node in ast.walk(func):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name) and node.func.id == call_name:
            return True
    return False


def _http_obsidian_tools_defined_under_flag(text: str, tool_names: list[str]) -> bool:
    tree = ast.parse(text)
    required_defs = {f"brain_{name}" for name in tool_names}
    found_defs: set[str] = set()

    for node in tree.body:
        if not isinstance(node, ast.If):
            continue
        cond = node.test
        if not (isinstance(cond, ast.Name) and cond.id == "ENABLE_HTTP_OBSIDIAN_TOOLS"):
            continue
        for stmt in node.body:
            if isinstance(stmt, ast.AsyncFunctionDef):
                if stmt.name in required_defs:
                    found_defs.add(stmt.name)
    return found_defs == required_defs


def _check_gateway_gating() -> list[str]:
    errors: list[str] = []
    text = GATEWAY_MAIN.read_text(encoding="utf-8")
    tree = ast.parse(text)
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    local_tools = payload.get("local_obsidian_tools", [])

    if 'OBSIDIAN_LOCAL_TOOLS_ENV = "ENABLE_LOCAL_OBSIDIAN_TOOLS"' not in text:
        errors.append("gateway must define ENABLE_LOCAL_OBSIDIAN_TOOLS env constant")
    if "_require_obsidian_local_tools_enabled" not in text:
        errors.append("gateway must guard local obsidian tools with _require_obsidian_local_tools_enabled")
    for tool in local_tools:
        fn_name = f"brain_{tool}"
        fn = _find_async_function(tree, fn_name)
        if fn is None:
            errors.append(f"missing function: {fn_name}")
            continue
        if not _function_calls_name(fn, "_require_obsidian_local_tools_enabled"):
            errors.append(f"{fn_name} must call _require_obsidian_local_tools_enabled()")

    required_caps = (
        '"obsidian": {',
        '"obsidian_local": {',
        '"mode": "local"',
    )
    for snippet in required_caps:
        if snippet not in text:
            errors.append(f"gateway capabilities missing snippet: {snippet}")
    return errors


def _check_http_transport_contract() -> list[str]:
    errors: list[str] = []
    text = HTTP_TRANSPORT.read_text(encoding="utf-8")
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    http_tools = payload.get("http_obsidian_tools", [])

    if "if ENABLE_HTTP_OBSIDIAN_TOOLS:" not in text:
        errors.append("HTTP transport must gate Obsidian tools with ENABLE_HTTP_OBSIDIAN_TOOLS")
    elif not _http_obsidian_tools_defined_under_flag(text, http_tools):
        errors.append(
            "HTTP transport must define all http_obsidian_tools under ENABLE_HTTP_OBSIDIAN_TOOLS gate"
        )
    required_caps = (
        '"obsidian": {',
        '"obsidian_http": {',
        '"mode": "http"',
    )
    for snippet in required_caps:
        if snippet not in text:
            errors.append(f"HTTP capabilities missing snippet: {snippet}")
    return errors


def main() -> int:
    errors: list[str] = []
    errors.extend(_check_manifest())
    errors.extend(_check_gateway_gating())
    errors.extend(_check_http_transport_contract())
    if errors:
        for err in errors:
            _fail(err)
        return 1
    print("Obsidian contract guardrail passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
