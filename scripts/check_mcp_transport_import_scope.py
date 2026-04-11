#!/usr/bin/env python3
"""Guardrail: keep mcp_transport imports limited to approved files."""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
CONTRACT = ROOT / "unified" / "contracts" / "mcp_transport_import_scope_contract.json"


def _fail(message: str) -> int:
    print(f"[FAIL] {message}", file=sys.stderr)
    return 1


def _is_mcp_transport_import(node: ast.AST) -> bool:
    if isinstance(node, ast.Import):
        for alias in node.names:
            if alias.name in {
                "mcp_transport",
                "src.mcp_transport",
                "unified.src.mcp_transport",
            }:
                return True
        return False

    if not isinstance(node, ast.ImportFrom):
        return False

    names = {alias.name for alias in node.names}
    if "mcp_transport" in names:
        if node.module in {None, "", "src", "unified.src"}:
            return True
    if node.module in {"src.mcp_transport", "unified.src.mcp_transport"}:
        return True
    return False


def _load_contract() -> dict[str, object]:
    payload = json.loads(CONTRACT.read_text(encoding="utf-8"))

    required_keys = {
        "scan_dirs",
        "required_runtime_importers",
        "allowed_runtime_importers",
        "allowed_test_importer_prefix",
    }
    missing = sorted(required_keys - set(payload.keys()))
    if missing:
        raise ValueError(f"contract missing keys: {missing}")

    for key in ("scan_dirs", "required_runtime_importers", "allowed_runtime_importers"):
        value = payload.get(key)
        if not isinstance(value, list) or not value or any(
            not isinstance(item, str) or not item.strip() for item in value
        ):
            raise ValueError(f"contract {key} must be a non-empty string list")

    test_prefix = payload.get("allowed_test_importer_prefix")
    if not isinstance(test_prefix, str) or not test_prefix.strip():
        raise ValueError("contract allowed_test_importer_prefix must be non-empty string")

    return payload


def _discover_importers(scan_dirs: list[str]) -> list[str]:
    importers: list[str] = []
    for rel_dir in scan_dirs:
        scan_dir = ROOT / rel_dir
        if not scan_dir.exists():
            continue
        for path in scan_dir.rglob("*.py"):
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source)
            if any(_is_mcp_transport_import(node) for node in ast.walk(tree)):
                importers.append(path.relative_to(ROOT).as_posix())
    return sorted(importers)


def _check_import_scope(importers: list[str], contract: dict[str, object]) -> list[str]:
    errors: list[str] = []
    required_importers = set(contract["required_runtime_importers"])
    allowed_importers = set(contract["allowed_runtime_importers"])
    allowed_test_prefix = str(contract["allowed_test_importer_prefix"])

    for required in sorted(required_importers):
        if required not in importers:
            errors.append(f"{required} must import mcp_transport")

    for path in importers:
        if path in allowed_importers:
            continue
        if path.startswith(allowed_test_prefix):
            continue
        errors.append(
            "mcp_transport import outside approved scope: "
            f"{path} (allowed: {sorted(allowed_importers)} + {allowed_test_prefix}*)"
        )
    return errors


def main() -> int:
    try:
        contract = _load_contract()
        importers = _discover_importers(list(contract["scan_dirs"]))
        errors = _check_import_scope(importers, contract)
    except Exception as exc:
        _fail(f"mcp transport import scope check failed: {exc}")
        return 1

    if errors:
        for error in errors:
            _fail(error)
        return 1

    print("MCP transport import scope guardrail passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
