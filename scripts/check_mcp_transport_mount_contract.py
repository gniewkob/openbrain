#!/usr/bin/env python3
"""Guardrail: enforce combined.py mount contract for compatibility transport."""

from __future__ import annotations

import ast
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
COMBINED = ROOT / "unified" / "src" / "combined.py"


def _fail(message: str) -> int:
    print(f"[FAIL] {message}", file=sys.stderr)
    return 1


def _imports_mcp_transport(tree: ast.Module) -> bool:
    for node in tree.body:
        if not isinstance(node, ast.ImportFrom):
            continue
        if node.module != "":
            # For relative form "from . import mcp_transport", ast module is None.
            if node.module is not None:
                continue
        if node.level != 1:
            continue
        if any(alias.name == "mcp_transport" for alias in node.names):
            return True
    return False


def _assigns_mcp_app_from_transport(tree: ast.Module) -> bool:
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(t, ast.Name) and t.id == "mcp_app" for t in node.targets):
            continue
        value = node.value
        if not isinstance(value, ast.Call):
            continue
        if not isinstance(value.func, ast.Attribute):
            continue
        if value.func.attr != "streamable_http_app":
            continue
        left = value.func.value
        if (
            isinstance(left, ast.Attribute)
            and isinstance(left.value, ast.Name)
            and left.value.id == "mcp_transport"
            and left.attr == "mcp"
        ):
            return True
    return False


def _root_redirect_reads_transport_path(tree: ast.Module) -> bool:
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not any(
            isinstance(target, ast.Name) and target.id == "streamable_http_path"
            for target in node.targets
        ):
            continue
        value = node.value
        if (
            isinstance(value, ast.Attribute)
            and isinstance(value.value, ast.Name)
            and value.value.id == "mcp_transport"
            and value.attr == "STREAMABLE_HTTP_PATH"
        ):
            return True
    return False


def _check_mount_contract(source: str) -> list[str]:
    errors: list[str] = []
    tree = ast.parse(source)

    if not _imports_mcp_transport(tree):
        errors.append("combined.py must import mcp_transport via relative import")
    if not _assigns_mcp_app_from_transport(tree):
        errors.append(
            "combined.py must assign mcp_app = mcp_transport.mcp.streamable_http_app()"
        )
    if not _root_redirect_reads_transport_path(tree):
        errors.append(
            "combined.py root redirect must read mcp_transport.STREAMABLE_HTTP_PATH"
        )
    return errors


def main() -> int:
    try:
        source = COMBINED.read_text(encoding="utf-8")
        errors = _check_mount_contract(source)
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
