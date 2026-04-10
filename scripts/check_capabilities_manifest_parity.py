#!/usr/bin/env python3
"""Guardrail: ensure capabilities manifest loaders stay in parity across transports."""

from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
HTTP_MANIFEST = ROOT / "unified/src/capabilities_manifest.py"
GATEWAY_MANIFEST = ROOT / "unified/mcp-gateway/src/capabilities_manifest.py"


def _fail(message: str) -> int:
    print(f"[FAIL] {message}", file=sys.stderr)
    return 1


def _extract_assignment_literal(tree: ast.AST, name: str) -> Any:
    for node in getattr(tree, "body", []):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    return ast.literal_eval(node.value)
        if isinstance(node, ast.AnnAssign):
            target = node.target
            if isinstance(target, ast.Name) and target.id == name and node.value is not None:
                return ast.literal_eval(node.value)
    raise ValueError(f"{name} assignment not found")


def _extract_contract_filename(tree: ast.AST) -> str:
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef) or node.name != "load_capabilities_manifest":
            continue
        for sub in ast.walk(node):
            if not isinstance(sub, ast.Constant) or not isinstance(sub.value, str):
                continue
            if sub.value.endswith(".json"):
                return sub.value
    raise ValueError("contract filename not found in load_capabilities_manifest")


def _check_manifest_parity(http_src: str, gateway_src: str) -> list[str]:
    errors: list[str] = []
    http_tree = ast.parse(http_src)
    gateway_tree = ast.parse(gateway_src)

    http_defaults = _extract_assignment_literal(http_tree, "_DEFAULTS")
    gateway_defaults = _extract_assignment_literal(gateway_tree, "_DEFAULTS")
    if http_defaults != gateway_defaults:
        errors.append("capabilities manifest _DEFAULTS must stay identical in HTTP and gateway modules")

    http_filename = _extract_contract_filename(http_tree)
    gateway_filename = _extract_contract_filename(gateway_tree)
    if http_filename != gateway_filename:
        errors.append("load_capabilities_manifest must resolve the same contract filename in HTTP and gateway modules")
    if http_filename != "capabilities_manifest.json":
        errors.append("load_capabilities_manifest must resolve capabilities_manifest.json")

    return errors


def main() -> int:
    http_src = HTTP_MANIFEST.read_text(encoding="utf-8")
    gateway_src = GATEWAY_MANIFEST.read_text(encoding="utf-8")
    errors = _check_manifest_parity(http_src, gateway_src)
    if errors:
        for err in errors:
            _fail(err)
        return 1
    print("Capabilities manifest parity guardrail passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
