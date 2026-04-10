#!/usr/bin/env python3
"""Guardrail: keep request/runtimes contract loaders in parity across transports."""

from __future__ import annotations

import ast
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
HTTP_REQUEST_BUILDERS = ROOT / "unified/src/request_builders.py"
GATEWAY_REQUEST_BUILDERS = ROOT / "unified/mcp-gateway/src/request_builders.py"
HTTP_RUNTIME_LIMITS = ROOT / "unified/src/runtime_limits.py"
GATEWAY_RUNTIME_LIMITS = ROOT / "unified/mcp-gateway/src/runtime_limits.py"


def _fail(message: str) -> int:
    print(f"[FAIL] {message}", file=sys.stderr)
    return 1


def _extract_value_error_messages(tree: ast.AST, fn_name: str) -> list[str]:
    for node in getattr(tree, "body", []):
        if not isinstance(node, ast.FunctionDef) or node.name != fn_name:
            continue
        messages: list[str] = []
        for sub in ast.walk(node):
            if not isinstance(sub, ast.Raise):
                continue
            exc = sub.exc
            if not isinstance(exc, ast.Call):
                continue
            if not isinstance(exc.func, ast.Name) or exc.func.id != "ValueError":
                continue
            if not exc.args:
                continue
            msg = exc.args[0]
            if isinstance(msg, ast.Constant) and isinstance(msg.value, str):
                messages.append(msg.value)
        return sorted(messages)
    raise ValueError(f"{fn_name} not found")


def _extract_contract_filename(tree: ast.AST, fn_name: str) -> str:
    for node in getattr(tree, "body", []):
        if not isinstance(node, ast.FunctionDef) or node.name != fn_name:
            continue
        for sub in ast.walk(node):
            if not isinstance(sub, ast.Constant) or not isinstance(sub.value, str):
                continue
            if sub.value.endswith(".json"):
                return sub.value
    raise ValueError(f"contract filename not found in {fn_name}")


def _extract_function_source(tree: ast.AST, source: str, fn_name: str) -> str:
    for node in getattr(tree, "body", []):
        if isinstance(node, ast.FunctionDef) and node.name == fn_name:
            snippet = ast.get_source_segment(source, node)
            if isinstance(snippet, str):
                return snippet.strip()
            break
    raise ValueError(f"{fn_name} not found")


def _extract_dict_literal_source(tree: ast.AST, source: str, var_name: str) -> str:
    for node in getattr(tree, "body", []):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == var_name:
                snippet = ast.get_source_segment(source, node.value)
                if isinstance(snippet, str):
                    return snippet.strip()
    raise ValueError(f"{var_name} assignment not found")


def _check_request_contract_parity(http_src: str, gateway_src: str) -> list[str]:
    errors: list[str] = []
    http_tree = ast.parse(http_src)
    gateway_tree = ast.parse(gateway_src)

    if _extract_function_source(http_tree, http_src, "_validate_request_contracts") != _extract_function_source(
        gateway_tree,
        gateway_src,
        "_validate_request_contracts",
    ):
        errors.append(
            "_validate_request_contracts logic must stay identical in HTTP and gateway modules"
        )

    if _extract_value_error_messages(http_tree, "_validate_request_contracts") != _extract_value_error_messages(
        gateway_tree,
        "_validate_request_contracts",
    ):
        errors.append(
            "_validate_request_contracts ValueError semantics must stay identical in HTTP and gateway modules"
        )

    http_filename = _extract_contract_filename(http_tree, "_load_request_contracts")
    gateway_filename = _extract_contract_filename(gateway_tree, "_load_request_contracts")
    if http_filename != gateway_filename:
        errors.append(
            "_load_request_contracts must resolve the same contract filename in HTTP and gateway modules"
        )
    if http_filename != "request_contracts.json":
        errors.append("_load_request_contracts must resolve request_contracts.json")

    return errors


def _check_runtime_limits_parity(http_src: str, gateway_src: str) -> list[str]:
    errors: list[str] = []
    http_tree = ast.parse(http_src)
    gateway_tree = ast.parse(gateway_src)

    if _extract_dict_literal_source(http_tree, http_src, "_DEFAULTS") != _extract_dict_literal_source(
        gateway_tree,
        gateway_src,
        "_DEFAULTS",
    ):
        errors.append("_DEFAULTS must stay identical in HTTP and gateway runtime limits")

    if _extract_function_source(http_tree, http_src, "_validate_runtime_limits") != _extract_function_source(
        gateway_tree,
        gateway_src,
        "_validate_runtime_limits",
    ):
        errors.append(
            "_validate_runtime_limits logic must stay identical in HTTP and gateway modules"
        )

    if _extract_value_error_messages(http_tree, "_validate_runtime_limits") != _extract_value_error_messages(
        gateway_tree,
        "_validate_runtime_limits",
    ):
        errors.append(
            "_validate_runtime_limits ValueError semantics must stay identical in HTTP and gateway modules"
        )

    http_filename = _extract_contract_filename(http_tree, "load_runtime_limits")
    gateway_filename = _extract_contract_filename(gateway_tree, "load_runtime_limits")
    if http_filename != gateway_filename:
        errors.append(
            "load_runtime_limits must resolve the same contract filename in HTTP and gateway modules"
        )
    if http_filename != "runtime_limits.json":
        errors.append("load_runtime_limits must resolve runtime_limits.json")

    return errors


def main() -> int:
    http_request_src = HTTP_REQUEST_BUILDERS.read_text(encoding="utf-8")
    gateway_request_src = GATEWAY_REQUEST_BUILDERS.read_text(encoding="utf-8")
    http_runtime_src = HTTP_RUNTIME_LIMITS.read_text(encoding="utf-8")
    gateway_runtime_src = GATEWAY_RUNTIME_LIMITS.read_text(encoding="utf-8")

    errors: list[str] = []
    errors.extend(_check_request_contract_parity(http_request_src, gateway_request_src))
    errors.extend(_check_runtime_limits_parity(http_runtime_src, gateway_runtime_src))
    if errors:
        for err in errors:
            _fail(err)
        return 1
    print("Request/runtime contract parity guardrail passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
