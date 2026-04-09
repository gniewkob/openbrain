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


def _extract_load_manifest_contract_path_parts(tree: ast.AST) -> list[str]:
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef) or node.name != "load_capabilities_manifest":
            continue
        for assign in node.body:
            if not isinstance(assign, ast.Assign):
                continue
            if len(assign.targets) != 1 or not isinstance(assign.targets[0], ast.Name):
                continue
            if assign.targets[0].id != "manifest_path":
                continue
            value = assign.value
            parts: list[str] = []
            for const in ast.walk(value):
                if isinstance(const, ast.Constant) and isinstance(const.value, str):
                    parts.append(const.value)
            return sorted(parts)
    raise ValueError("manifest_path assignment not found in load_capabilities_manifest")


def _check_manifest_parity(http_src: str, gateway_src: str) -> list[str]:
    errors: list[str] = []
    http_tree = ast.parse(http_src)
    gateway_tree = ast.parse(gateway_src)

    http_defaults = _extract_assignment_literal(http_tree, "_DEFAULTS")
    gateway_defaults = _extract_assignment_literal(gateway_tree, "_DEFAULTS")
    if http_defaults != gateway_defaults:
        errors.append("capabilities manifest _DEFAULTS must stay identical in HTTP and gateway modules")

    http_parts = _extract_load_manifest_contract_path_parts(http_tree)
    gateway_parts = _extract_load_manifest_contract_path_parts(gateway_tree)
    if http_parts != gateway_parts:
        errors.append("load_capabilities_manifest path semantics must stay identical in HTTP and gateway modules")
    if "contracts" not in http_parts or "capabilities_manifest.json" not in http_parts:
        errors.append("load_capabilities_manifest must resolve contracts/capabilities_manifest.json")

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
