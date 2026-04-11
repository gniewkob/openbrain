#!/usr/bin/env python3
"""Guardrail: keep mcp_transport imports limited to approved files."""

from __future__ import annotations

import ast
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SCAN_DIRS = (ROOT / "unified", ROOT / "scripts")
ALLOWED_IMPORTERS = {
    "unified/src/combined.py",
}
ALLOWED_TEST_PREFIX = "unified/tests/"


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


def _discover_importers() -> list[str]:
    importers: list[str] = []
    for scan_dir in SCAN_DIRS:
        if not scan_dir.exists():
            continue
        for path in scan_dir.rglob("*.py"):
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source)
            if any(_is_mcp_transport_import(node) for node in ast.walk(tree)):
                importers.append(path.relative_to(ROOT).as_posix())
    return sorted(importers)


def _check_import_scope(importers: list[str]) -> list[str]:
    errors: list[str] = []
    if "unified/src/combined.py" not in importers:
        errors.append("unified/src/combined.py must import mcp_transport")

    for path in importers:
        if path in ALLOWED_IMPORTERS:
            continue
        if path.startswith(ALLOWED_TEST_PREFIX):
            continue
        errors.append(
            "mcp_transport import outside approved scope: "
            f"{path} (allowed: {sorted(ALLOWED_IMPORTERS)} + {ALLOWED_TEST_PREFIX}*)"
        )
    return errors


def main() -> int:
    try:
        importers = _discover_importers()
        errors = _check_import_scope(importers)
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
