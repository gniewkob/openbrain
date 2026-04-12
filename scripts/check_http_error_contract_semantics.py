#!/usr/bin/env python3
"""Guardrail: enforce critical semantics in http_error_contracts.json."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
CONTRACT_PATH = ROOT / "unified" / "contracts" / "http_error_contracts.json"
GUARDRAIL_CONTRACT_PATH = (
    ROOT / "unified" / "contracts" / "http_error_contract_guardrail_contract.json"
)


def _fail(message: str) -> int:
    print(f"[FAIL] {message}", file=sys.stderr)
    return 1


def _load_contract(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_guardrail_contract(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("http_error_contract_guardrail_contract must be object")
    required_root_keys = payload.get("required_root_keys")
    required_status_label_keys = payload.get("required_status_label_keys")
    required_fallbacks = payload.get("required_fallbacks")
    required_missing_session_hint = payload.get("required_missing_session_hint")
    if not isinstance(required_root_keys, list) or not required_root_keys:
        raise ValueError("required_root_keys must be non-empty list")
    if any(not isinstance(item, str) or not item for item in required_root_keys):
        raise ValueError("required_root_keys must contain non-empty strings")
    if (
        not isinstance(required_status_label_keys, list)
        or not required_status_label_keys
    ):
        raise ValueError("required_status_label_keys must be non-empty list")
    if any(
        not isinstance(item, str) or not item for item in required_status_label_keys
    ):
        raise ValueError("required_status_label_keys must contain non-empty strings")
    if not isinstance(required_fallbacks, dict) or not required_fallbacks:
        raise ValueError("required_fallbacks must be non-empty object")
    for key, value in required_fallbacks.items():
        if not isinstance(key, str) or not key:
            raise ValueError("required_fallbacks keys must be non-empty strings")
        if not isinstance(value, str) or not value:
            raise ValueError("required_fallbacks values must be non-empty strings")
    if not isinstance(required_missing_session_hint, dict):
        raise ValueError("required_missing_session_hint must be object")
    for key in ("status_code", "contains", "message"):
        if key not in required_missing_session_hint:
            raise ValueError(f"required_missing_session_hint missing key: {key}")
    return payload


def _check_contract(data: dict[str, Any], guardrail: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    required_root_keys = {str(item) for item in guardrail["required_root_keys"]}
    required_status_labels = {
        str(item) for item in guardrail["required_status_label_keys"]
    }
    required_fallbacks = {
        str(key): str(value)
        for key, value in dict(guardrail["required_fallbacks"]).items()
    }
    required_detail_hint = dict(guardrail["required_missing_session_hint"])

    root_keys = set(data.keys())
    missing = required_root_keys - root_keys
    if missing:
        errors.append(f"missing root keys: {sorted(missing)}")

    status_labels = data.get("status_labels", {})
    if not isinstance(status_labels, dict):
        errors.append("status_labels must be an object")
    else:
        for key in sorted(required_status_labels):
            if key not in status_labels:
                errors.append(f"status_labels missing required key {key}")

    for key, expected in required_fallbacks.items():
        if data.get(key) != expected:
            errors.append(f"{key} must stay {expected!r}")

    detail_hints = data.get("detail_hints", {})
    if not isinstance(detail_hints, dict):
        errors.append("detail_hints must be an object")
        return errors

    missing_session = detail_hints.get("missing_session_id")
    if not isinstance(missing_session, dict):
        errors.append("detail_hints.missing_session_id must exist and be an object")
        return errors

    for key, expected in required_detail_hint.items():
        if missing_session.get(key) != expected:
            errors.append(
                f"detail_hints.missing_session_id.{key} drift: expected={expected!r} got={missing_session.get(key)!r}"
            )

    return errors


def main() -> int:
    try:
        data = _load_contract(CONTRACT_PATH)
        guardrail = _load_guardrail_contract(GUARDRAIL_CONTRACT_PATH)
    except Exception as exc:
        _fail(f"failed to load contract: {exc}")
        return 1
    errors = _check_contract(data, guardrail)
    if errors:
        for error in errors:
            _fail(error)
        return 1
    print("HTTP error contract semantics guardrail passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
