#!/usr/bin/env python3
"""Guardrail: enforce cleanup actor fallback semantics in V1 memory API."""

from __future__ import annotations

import ast
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
MEMORY_API = ROOT / "unified/src/api/v1/memory.py"


def _fail(message: str) -> int:
    print(f"[FAIL] {message}", file=sys.stderr)
    return 1


def _find_async_function(tree: ast.Module, name: str) -> ast.AsyncFunctionDef:
    for node in tree.body:
        if isinstance(node, ast.AsyncFunctionDef) and node.name == name:
            return node
    raise ValueError(f"{name} not found")


def _has_actor_fallback(fn: ast.AsyncFunctionDef) -> bool:
    for node in ast.walk(fn):
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(t, ast.Name) and t.id == "actor" for t in node.targets):
            continue
        value = node.value
        if not isinstance(value, ast.BoolOp) or not isinstance(value.op, ast.Or):
            continue
        if len(value.values) != 2:
            continue
        lhs, rhs = value.values
        if not (isinstance(rhs, ast.Constant) and rhs.value == "agent"):
            continue
        if not (
            isinstance(lhs, ast.Call)
            and isinstance(lhs.func, ast.Name)
            and lhs.func.id == "get_subject"
            and len(lhs.args) == 1
            and isinstance(lhs.args[0], ast.Name)
            and lhs.args[0].id == "_user"
        ):
            continue
        return True
    return False


def _forwards_actor_kwarg(fn: ast.AsyncFunctionDef) -> bool:
    for node in ast.walk(fn):
        if not isinstance(node, ast.Await) or not isinstance(node.value, ast.Call):
            continue
        call = node.value
        if not (
            isinstance(call.func, ast.Name)
            and call.func.id == "cleanup_build_test_data_use_case"
        ):
            continue
        for kw in call.keywords:
            if kw.arg == "actor" and isinstance(kw.value, ast.Name) and kw.value.id == "actor":
                return True
    return False


def _check_cleanup_actor_semantics(source: str) -> list[str]:
    tree = ast.parse(source)
    fn = _find_async_function(tree, "cleanup_build_test_data")
    errors: list[str] = []
    if not _has_actor_fallback(fn):
        errors.append(
            "cleanup_build_test_data must set actor via get_subject(_user) or 'agent'"
        )
    if not _forwards_actor_kwarg(fn):
        errors.append(
            "cleanup_build_test_data must forward actor=actor to cleanup_build_test_data_use_case"
        )
    return errors


def main() -> int:
    source = MEMORY_API.read_text(encoding="utf-8")
    errors = _check_cleanup_actor_semantics(source)
    if errors:
        for error in errors:
            _fail(error)
        return 1
    print("Cleanup actor semantics guardrail passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
