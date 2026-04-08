#!/usr/bin/env python3
"""Guardrail: enforce core audit semantics in API and write paths."""

from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SCHEMAS = ROOT / "unified/src/schemas.py"
API_V1_MEMORY = ROOT / "unified/src/api/v1/memory.py"
MEMORY_WRITES = ROOT / "unified/src/memory_writes.py"


def _fail(message: str) -> int:
    print(f"[FAIL] {message}", file=sys.stderr)
    return 1


def _extract_class_block(text: str, class_name: str) -> str:
    pattern = rf"^class {class_name}\(BaseModel\):\n(?P<body>(?:    .*\n)+)"
    match = re.search(pattern, text, flags=re.MULTILINE)
    if not match:
        raise RuntimeError(f"missing class definition: {class_name}")
    return match.group("body")


def _check_schemas() -> list[str]:
    errors: list[str] = []
    text = SCHEMAS.read_text(encoding="utf-8")
    try:
        write_block = _extract_class_block(text, "MemoryWriteRecord")
    except RuntimeError as exc:
        return [str(exc)]
    if "created_by" in write_block:
        errors.append("MemoryWriteRecord must not accept created_by from requests")
    if "updated_by" in write_block:
        errors.append("MemoryWriteRecord must not accept updated_by from requests")
    return errors


def _check_api_patch_override() -> list[str]:
    errors: list[str] = []
    text = API_V1_MEMORY.read_text(encoding="utf-8")
    required_snippet = 'safe_data = data.model_copy(update={"updated_by": actor})'
    if required_snippet not in text:
        errors.append(
            "PATCH endpoint must override request updated_by with authenticated actor"
        )
    return errors


def _check_write_path_actor_binding() -> list[str]:
    errors: list[str] = []
    text = MEMORY_WRITES.read_text(encoding="utf-8")
    required_snippets = (
        "created_by=actor,",
        '"updated_by": actor,',
        "created_by=existing.created_by,",
    )
    for snippet in required_snippets:
        if snippet not in text:
            errors.append(f"memory_writes.py missing required audit binding snippet: {snippet}")
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
