#!/usr/bin/env python3
"""Guardrail: enforce critical semantics in http_error_contracts.json."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
CONTRACT_PATH = ROOT / "unified" / "contracts" / "http_error_contracts.json"

REQUIRED_ROOT_KEYS = {
    "status_labels",
    "detail_hints",
    "fallback_5xx",
    "fallback_other",
}
REQUIRED_STATUS_LABELS = {"401", "403", "404", "422"}
REQUIRED_DETAIL_HINT = {
    "status_code": 400,
    "contains": "Missing session ID",
    "message": "Missing MCP session context; reconnect the MCP HTTP client and retry.",
}


def _fail(message: str) -> int:
    print(f"[FAIL] {message}", file=sys.stderr)
    return 1


def _load_contract(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _check_contract(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    root_keys = set(data.keys())
    missing = REQUIRED_ROOT_KEYS - root_keys
    if missing:
        errors.append(f"missing root keys: {sorted(missing)}")

    status_labels = data.get("status_labels", {})
    if not isinstance(status_labels, dict):
        errors.append("status_labels must be an object")
    else:
        for key in sorted(REQUIRED_STATUS_LABELS):
            if key not in status_labels:
                errors.append(f"status_labels missing required key {key}")

    fallback_5xx = data.get("fallback_5xx")
    if fallback_5xx != "Internal server error":
        errors.append("fallback_5xx must stay 'Internal server error'")

    fallback_other = data.get("fallback_other")
    if fallback_other != "Request failed":
        errors.append("fallback_other must stay 'Request failed'")

    detail_hints = data.get("detail_hints", {})
    if not isinstance(detail_hints, dict):
        errors.append("detail_hints must be an object")
        return errors

    missing_session = detail_hints.get("missing_session_id")
    if not isinstance(missing_session, dict):
        errors.append("detail_hints.missing_session_id must exist and be an object")
        return errors

    for key, expected in REQUIRED_DETAIL_HINT.items():
        if missing_session.get(key) != expected:
            errors.append(
                f"detail_hints.missing_session_id.{key} drift: expected={expected!r} got={missing_session.get(key)!r}"
            )

    return errors


def main() -> int:
    try:
        data = _load_contract(CONTRACT_PATH)
    except Exception as exc:
        _fail(f"failed to load contract: {exc}")
        return 1
    errors = _check_contract(data)
    if errors:
        for error in errors:
            _fail(error)
        return 1
    print("HTTP error contract semantics guardrail passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
