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


def _extract_contract_filename(tree: ast.AST) -> str:
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef) or node.name != "load_capabilities_metadata":
            continue
        for sub in ast.walk(node):
            if not isinstance(sub, ast.Constant) or not isinstance(sub.value, str):
                continue
            if sub.value.endswith(".json"):
                return sub.value
    raise ValueError("contract filename not found in load_capabilities_metadata")


def _check_metadata_parity(http_src: str, gateway_src: str) -> list[str]:
    errors: list[str] = []
    http_tree = ast.parse(http_src)
    gateway_tree = ast.parse(gateway_src)

    if _extract_semver_pattern(http_tree) != _extract_semver_pattern(gateway_tree):
        errors.append("_SEMVER pattern must stay identical in HTTP and gateway metadata modules")

    if _extract_validate_error_messages(http_tree) != _extract_validate_error_messages(gateway_tree):
        errors.append("_validate_metadata error semantics must stay identical in HTTP and gateway metadata modules")

    http_filename = _extract_contract_filename(http_tree)
    gateway_filename = _extract_contract_filename(gateway_tree)
    if http_filename != gateway_filename:
        errors.append("load_capabilities_metadata must resolve the same contract filename in HTTP and gateway modules")
    if http_filename != "capabilities_metadata.json":
        errors.append("load_capabilities_metadata must resolve capabilities_metadata.json")

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
