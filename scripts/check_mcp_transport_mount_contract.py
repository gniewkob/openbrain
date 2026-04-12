#!/usr/bin/env python3
"""Guardrail: enforce combined.py mount contract for compatibility transport."""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
COMBINED = ROOT / "unified" / "src" / "combined.py"
CONTRACT = ROOT / "unified" / "contracts" / "mcp_transport_mount_contract.json"


def _fail(message: str) -> int:
    print(f"[FAIL] {message}", file=sys.stderr)
    return 1


def _load_contract() -> dict[str, object]:
    payload = json.loads(CONTRACT.read_text(encoding="utf-8"))
    required_keys = {
        "required_import_name",
        "required_import_level",
        "required_mount_target",
        "required_mount_attr_chain",
        "required_redirect_target",
        "required_redirect_attr_chain",
    }
    missing = sorted(required_keys - set(payload.keys()))
    if missing:
        raise ValueError(f"contract missing keys: {missing}")
    for key in (
        "required_import_name",
        "required_mount_target",
        "required_redirect_target",
    ):
        value = payload.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"contract {key} must be non-empty string")
    for key in ("required_mount_attr_chain", "required_redirect_attr_chain"):
        value = payload.get(key)
        if not isinstance(value, list) or not value or any(
            not isinstance(item, str) or not item.strip() for item in value
        ):
            raise ValueError(f"contract {key} must be a non-empty string list")
    level = payload.get("required_import_level")
    if not isinstance(level, int) or level < 0:
        raise ValueError("contract required_import_level must be integer >= 0")
    return payload


def _imports_mcp_transport(tree: ast.Module, import_name: str, import_level: int) -> bool:
    for node in tree.body:
        if not isinstance(node, ast.ImportFrom):
            continue
        if node.module != "":
            # For relative form "from . import mcp_transport", ast module is None.
            if node.module is not None:
                continue
        if node.level != import_level:
            continue
        if any(alias.name == import_name for alias in node.names):
            return True
    return False


def _attr_chain(node: ast.AST) -> list[str]:
    if isinstance(node, ast.Name):
        return [node.id]
    if isinstance(node, ast.Attribute):
        return [*_attr_chain(node.value), node.attr]
    return []


def _assigns_mcp_app_from_transport(
    tree: ast.Module,
    target_name: str,
    expected_chain: list[str],
) -> bool:
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(
            isinstance(t, ast.Name) and t.id == target_name for t in node.targets
        ):
            continue
        value = node.value
        if not isinstance(value, ast.Call):
            continue
        if _attr_chain(value.func) == expected_chain:
            return True
    return False


def _root_redirect_reads_transport_path(
    tree: ast.Module,
    target_name: str,
    expected_chain: list[str],
) -> bool:
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not any(
            isinstance(target, ast.Name) and target.id == target_name
            for target in node.targets
        ):
            continue
        if _attr_chain(node.value) == expected_chain:
            return True
    return False


def _check_mount_contract(source: str, contract: dict[str, object]) -> list[str]:
    errors: list[str] = []
    tree = ast.parse(source)

    required_import_name = str(contract["required_import_name"])
    required_import_level = int(contract["required_import_level"])
    required_mount_target = str(contract["required_mount_target"])
    required_mount_chain = [str(item) for item in contract["required_mount_attr_chain"]]
    required_redirect_target = str(contract["required_redirect_target"])
    required_redirect_chain = [
        str(item) for item in contract["required_redirect_attr_chain"]
    ]

    if not _imports_mcp_transport(tree, required_import_name, required_import_level):
        errors.append("combined.py must import mcp_transport via relative import")
    if not _assigns_mcp_app_from_transport(
        tree,
        required_mount_target,
        required_mount_chain,
    ):
        errors.append(
            "combined.py must assign mcp_app = mcp_transport.mcp.streamable_http_app()"
        )
    if not _root_redirect_reads_transport_path(
        tree,
        required_redirect_target,
        required_redirect_chain,
    ):
        errors.append(
            "combined.py root redirect must read mcp_transport.STREAMABLE_HTTP_PATH"
        )
    return errors


def main() -> int:
    try:
        contract = _load_contract()
        source = COMBINED.read_text(encoding="utf-8")
        errors = _check_mount_contract(source, contract)
    except Exception as exc:
        _fail(f"mcp transport mount contract check failed: {exc}")
        return 1

    if errors:
        for err in errors:
            _fail(err)
        return 1
    print("MCP transport mount contract guardrail passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
