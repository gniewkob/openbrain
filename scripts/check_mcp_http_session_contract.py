#!/usr/bin/env python3
"""Guardrail: enforce MCP HTTP streamable session contract invariants."""

from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MCP_HTTP = ROOT / "unified" / "mcp-gateway" / "src" / "mcp_http.py"
RUNBOOK = ROOT / "docs" / "runbook-test-data-hygiene.md"


def _parse_module(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def _extract_mcp_run_kwargs(tree: ast.Module) -> dict[str, str]:
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr != "run":
            continue
        if not isinstance(node.func.value, ast.Name):
            continue
        if node.func.value.id != "mcp":
            continue

        kwargs: dict[str, str] = {}
        for kw in node.keywords:
            if kw.arg is None:
                continue
            if isinstance(kw.value, ast.Constant):
                kwargs[kw.arg] = str(kw.value.value)
        return kwargs
    return {}


def _has_custom_route(tree: ast.Module, path: str) -> bool:
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for deco in node.decorator_list:
            if not isinstance(deco, ast.Call):
                continue
            if not isinstance(deco.func, ast.Attribute):
                continue
            if deco.func.attr != "custom_route":
                continue
            if not deco.args:
                continue
            arg0 = deco.args[0]
            if isinstance(arg0, ast.Constant) and arg0.value == path:
                return True
    return False


def _check_mcp_http_contract() -> list[str]:
    tree = _parse_module(MCP_HTTP)
    errors: list[str] = []

    run_kwargs = _extract_mcp_run_kwargs(tree)
    if not run_kwargs:
        errors.append("mcp_http.py must call mcp.run(...)")
        return errors

    if run_kwargs.get("transport") != "streamable-http":
        errors.append("mcp.run transport must be 'streamable-http'")

    if run_kwargs.get("path") != "/":
        errors.append("mcp.run path must stay '/' for streamable session compatibility")

    if not _has_custom_route(tree, "/consent"):
        errors.append("mcp_http.py must expose /consent custom route")

    if not _has_custom_route(tree, "/.well-known/openid-configuration"):
        errors.append(
            "mcp_http.py must expose /.well-known/openid-configuration custom route"
        )

    return errors


def _check_runbook() -> list[str]:
    text = RUNBOOK.read_text(encoding="utf-8")
    if "Missing session ID" not in text:
        return ["runbook-test-data-hygiene.md must document 'Missing session ID'"]
    return []


def main() -> int:
    errors = [*_check_mcp_http_contract(), *_check_runbook()]
    if errors:
        print("MCP HTTP session contract guardrail failed:")
        for err in errors:
            print(f"- {err}")
        return 1
    print("MCP HTTP session contract guardrail passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
