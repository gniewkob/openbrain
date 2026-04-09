#!/usr/bin/env python3
"""Guardrail: ensure capabilities metadata loaders stay in parity across transports."""

from __future__ import annotations

import ast
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
HTTP_METADATA = ROOT / "unified/src/capabilities_metadata.py"
GATEWAY_METADATA = ROOT / "unified/mcp-gateway/src/capabilities_metadata.py"


def _fail(message: str) -> int:
    print(f"[FAIL] {message}", file=sys.stderr)
    return 1


def _extract_semver_pattern(tree: ast.AST) -> str:
    for node in getattr(tree, "body", []):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "_SEMVER":
                    for sub in ast.walk(node.value):
                        if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                            return sub.value
    raise ValueError("_SEMVER assignment not found")


def _extract_validate_error_messages(tree: ast.AST) -> list[str]:
    messages: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Raise):
            continue
        exc = node.exc
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


def _extract_contract_path_tokens(tree: ast.AST) -> list[str]:
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef) or node.name != "load_capabilities_metadata":
            continue
        for assign in node.body:
            if not isinstance(assign, ast.Assign):
                continue
            if len(assign.targets) != 1 or not isinstance(assign.targets[0], ast.Name):
                continue
            if assign.targets[0].id != "contract_path":
                continue
            tokens: list[str] = []
            for sub in ast.walk(assign.value):
                if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                    tokens.append(sub.value)
            return sorted(tokens)
    raise ValueError("contract_path assignment not found in load_capabilities_metadata")


def _check_metadata_parity(http_src: str, gateway_src: str) -> list[str]:
    errors: list[str] = []
    http_tree = ast.parse(http_src)
    gateway_tree = ast.parse(gateway_src)

    if _extract_semver_pattern(http_tree) != _extract_semver_pattern(gateway_tree):
        errors.append("_SEMVER pattern must stay identical in HTTP and gateway metadata modules")

    if _extract_validate_error_messages(http_tree) != _extract_validate_error_messages(gateway_tree):
        errors.append("_validate_metadata error semantics must stay identical in HTTP and gateway metadata modules")

    http_tokens = _extract_contract_path_tokens(http_tree)
    gateway_tokens = _extract_contract_path_tokens(gateway_tree)
    if http_tokens != gateway_tokens:
        errors.append("load_capabilities_metadata path semantics must stay identical in HTTP and gateway modules")
    if "contracts" not in http_tokens or "capabilities_metadata.json" not in http_tokens:
        errors.append("load_capabilities_metadata must resolve contracts/capabilities_metadata.json")

    return errors


def main() -> int:
    http_src = HTTP_METADATA.read_text(encoding="utf-8")
    gateway_src = GATEWAY_METADATA.read_text(encoding="utf-8")
    errors = _check_metadata_parity(http_src, gateway_src)
    if errors:
        for err in errors:
            _fail(err)
        return 1
    print("Capabilities metadata parity guardrail passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
