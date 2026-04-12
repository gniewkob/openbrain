#!/usr/bin/env python3
"""Guardrail: enforce MCP HTTP streamable session contract invariants."""

from __future__ import annotations

import ast
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MCP_HTTP = ROOT / "unified" / "mcp-gateway" / "src" / "mcp_http.py"
RUNBOOK = ROOT / "docs" / "runbook-test-data-hygiene.md"
CONTRACT = ROOT / "unified" / "contracts" / "mcp_http_session_contract.json"


def _parse_module(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def _load_contract() -> dict[str, object]:
    payload = json.loads(CONTRACT.read_text(encoding="utf-8"))
    required_keys = {
        "required_run_kwargs",
        "required_custom_routes",
        "require_main_entrypoint_call",
        "runbook_required_snippets",
    }
    missing = sorted(required_keys - set(payload.keys()))
    if missing:
        raise ValueError(f"contract missing keys: {missing}")

    run_kwargs = payload.get("required_run_kwargs")
    if not isinstance(run_kwargs, dict) or not run_kwargs:
        raise ValueError("contract required_run_kwargs must be a non-empty object")
    for key, value in run_kwargs.items():
        if not isinstance(key, str) or not key:
            raise ValueError("contract required_run_kwargs keys must be non-empty strings")
        if not isinstance(value, str) or not value:
            raise ValueError("contract required_run_kwargs values must be non-empty strings")

    required_routes = payload.get("required_custom_routes")
    if not isinstance(required_routes, list) or not required_routes:
        raise ValueError("contract required_custom_routes must be a non-empty list")
    if any(not isinstance(route, str) or not route for route in required_routes):
        raise ValueError("contract required_custom_routes must contain non-empty strings")

    if not isinstance(payload.get("require_main_entrypoint_call"), bool):
        raise ValueError("contract require_main_entrypoint_call must be bool")

    runbook_snippets = payload.get("runbook_required_snippets")
    if not isinstance(runbook_snippets, list) or not runbook_snippets:
        raise ValueError("contract runbook_required_snippets must be a non-empty list")
    if any(not isinstance(snippet, str) or not snippet for snippet in runbook_snippets):
        raise ValueError("contract runbook_required_snippets must contain non-empty strings")

    return payload


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


def _has_main_entrypoint_call(tree: ast.Module) -> bool:
    for node in tree.body:
        if not isinstance(node, ast.If):
            continue
        test = node.test
        if not isinstance(test, ast.Compare):
            continue
        if not isinstance(test.left, ast.Name) or test.left.id != "__name__":
            continue
        if len(test.ops) != 1 or not isinstance(test.ops[0], ast.Eq):
            continue
        if len(test.comparators) != 1:
            continue
        comparator = test.comparators[0]
        if not isinstance(comparator, ast.Constant) or comparator.value != "__main__":
            continue
        for statement in node.body:
            if not isinstance(statement, ast.Expr):
                continue
            if not isinstance(statement.value, ast.Call):
                continue
            call = statement.value
            if isinstance(call.func, ast.Name) and call.func.id == "main":
                return True
    return False


def _check_mcp_http_contract(contract: dict[str, object]) -> list[str]:
    tree = _parse_module(MCP_HTTP)
    errors: list[str] = []

    run_kwargs = _extract_mcp_run_kwargs(tree)
    if not run_kwargs:
        errors.append("mcp_http.py must call mcp.run(...)")
        return errors

    required_run_kwargs = dict(contract["required_run_kwargs"])
    for key, expected in required_run_kwargs.items():
        if run_kwargs.get(key) != expected:
            errors.append(f"mcp.run {key} must be '{expected}'")

    for route in list(contract["required_custom_routes"]):
        if not _has_custom_route(tree, route):
            errors.append(f"mcp_http.py must expose {route} custom route")

    if contract["require_main_entrypoint_call"] and not _has_main_entrypoint_call(tree):
        errors.append("mcp_http.py must call main() from __main__ entrypoint")

    return errors


def _check_runbook(contract: dict[str, object]) -> list[str]:
    text = RUNBOOK.read_text(encoding="utf-8")
    errors: list[str] = []
    for snippet in list(contract["runbook_required_snippets"]):
        if snippet not in text:
            errors.append(f"runbook-test-data-hygiene.md must document '{snippet}'")
    return errors


def main() -> int:
    try:
        contract = _load_contract()
    except Exception as exc:
        print("MCP HTTP session contract guardrail failed:")
        print(f"- contract load failed: {exc}")
        return 1
    errors = [*_check_mcp_http_contract(contract), *_check_runbook(contract)]
    if errors:
        print("MCP HTTP session contract guardrail failed:")
        for err in errors:
            print(f"- {err}")
        return 1
    print("MCP HTTP session contract guardrail passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
