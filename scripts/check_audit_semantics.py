#!/usr/bin/env python3
"""Guardrail: enforce core audit semantics in API and write paths."""

from __future__ import annotations

import re
import sys
import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SCHEMAS = ROOT / "unified/src/schemas.py"
API_V1_MEMORY = ROOT / "unified/src/api/v1/memory.py"
MEMORY_WRITES = ROOT / "unified/src/memory_writes.py"


def _fail(message: str) -> int:
    print(f"[FAIL] {message}", file=sys.stderr)
    return 1


def _field_names_in_class(text: str, class_name: str) -> set[str]:
    """Return annotated field names for a class using AST parsing."""
    tree = ast.parse(text)
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        if node.name != class_name:
            continue
        names: set[str] = set()
        for stmt in node.body:
            if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                names.add(stmt.target.id)
            elif isinstance(stmt, ast.Assign):
                for target in stmt.targets:
                    if isinstance(target, ast.Name):
                        names.add(target.id)
        return names
    raise RuntimeError(f"missing class definition: {class_name}")


def _has_patch_actor_override(text: str) -> bool:
    """Ensure PATCH endpoint binds updated_by to authenticated actor."""
    tree = ast.parse(text)
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name != "v1_update":
            continue

        saw_safe_data_override = False
        uses_safe_data_in_update_call = False

        for stmt in ast.walk(node):
            if isinstance(stmt, ast.Assign):
                if len(stmt.targets) != 1 or not isinstance(stmt.targets[0], ast.Name):
                    continue
                if stmt.targets[0].id != "safe_data":
                    continue
                call = stmt.value
                if not isinstance(call, ast.Call):
                    continue
                if not (
                    isinstance(call.func, ast.Attribute)
                    and call.func.attr == "model_copy"
                    and isinstance(call.func.value, ast.Name)
                    and call.func.value.id == "data"
                ):
                    continue
                for kw in call.keywords:
                    if kw.arg != "update" or not isinstance(kw.value, ast.Dict):
                        continue
                    for key, value in zip(kw.value.keys, kw.value.values):
                        if (
                            isinstance(key, ast.Constant)
                            and key.value == "updated_by"
                            and isinstance(value, ast.Name)
                            and value.id == "actor"
                        ):
                            saw_safe_data_override = True

            if isinstance(stmt, ast.Call):
                if not (isinstance(stmt.func, ast.Name) and stmt.func.id == "update_memory"):
                    continue
                if len(stmt.args) >= 3 and isinstance(stmt.args[2], ast.Name):
                    if stmt.args[2].id == "safe_data":
                        uses_safe_data_in_update_call = True

        return saw_safe_data_override and uses_safe_data_in_update_call
    return False


def _check_schemas() -> list[str]:
    errors: list[str] = []
    text = SCHEMAS.read_text(encoding="utf-8")
    try:
        write_fields = _field_names_in_class(text, "MemoryWriteRecord")
    except RuntimeError as exc:
        return [str(exc)]
    if "created_by" in write_fields:
        errors.append("MemoryWriteRecord must not accept created_by from requests")
    if "updated_by" in write_fields:
        errors.append("MemoryWriteRecord must not accept updated_by from requests")
    return errors


def _check_api_patch_override() -> list[str]:
    errors: list[str] = []
    text = API_V1_MEMORY.read_text(encoding="utf-8")
    if not _has_patch_actor_override(text):
        errors.append(
            "PATCH endpoint must override request updated_by with authenticated actor"
        )
    return errors


def _check_write_path_actor_binding() -> list[str]:
    errors: list[str] = []
    text = MEMORY_WRITES.read_text(encoding="utf-8")
    required_patterns = (
        r"created_by\s*=\s*actor",
        r'"updated_by"\s*:\s*actor',
        r"created_by\s*=\s*existing\.created_by",
    )
    for pattern in required_patterns:
        if not re.search(pattern, text):
            errors.append(
                f"memory_writes.py missing required audit binding pattern: {pattern}"
            )
    return errors


def main() -> int:
    errors: list[str] = []
    errors.extend(_check_schemas())
    errors.extend(_check_api_patch_override())
    errors.extend(_check_write_path_actor_binding())
    if errors:
        for err in errors:
            _fail(err)
        return 1
    print("Audit semantics guardrail passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
