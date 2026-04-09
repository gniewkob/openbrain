#!/usr/bin/env python3
"""Guardrail: enforce export redaction contract invariants."""

from __future__ import annotations

import ast
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
CRUD_COMMON = ROOT / "unified/src/crud_common.py"

REQUIRED_SENSITIVITIES = {"public", "internal", "confidential", "restricted"}
REQUIRED_POLICY_KEYS = {"allow_fields", "redact_content", "allow_tags", "allow_match_key"}


def _fail(message: str) -> int:
    print(f"[FAIL] {message}", file=sys.stderr)
    return 1


def _load_source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _extract_export_policy(text: str) -> dict[str, dict]:
    tree = ast.parse(text)
    for node in tree.body:
        if isinstance(node, ast.Assign):
            if len(node.targets) != 1:
                continue
            target = node.targets[0]
            if isinstance(target, ast.Name) and target.id == "EXPORT_POLICY":
                return ast.literal_eval(node.value)
        elif isinstance(node, ast.AnnAssign):
            target = node.target
            if isinstance(target, ast.Name) and target.id == "EXPORT_POLICY":
                if node.value is None:
                    raise ValueError("EXPORT_POLICY annotated assignment missing value")
                return ast.literal_eval(node.value)
    raise ValueError("EXPORT_POLICY assignment not found")


def _check_export_policy_semantics(text: str) -> list[str]:
    errors: list[str] = []
    try:
        policy = _extract_export_policy(text)
    except Exception as exc:
        return [f"unable to parse EXPORT_POLICY: {exc}"]

    sensitivities = set(policy.keys())
    if sensitivities != REQUIRED_SENSITIVITIES:
        errors.append(
            "EXPORT_POLICY sensitivities must be exactly "
            f"{sorted(REQUIRED_SENSITIVITIES)} (got {sorted(sensitivities)})"
        )
        return errors

    for sensitivity, rules in policy.items():
        rule_keys = set(rules.keys())
        if rule_keys != REQUIRED_POLICY_KEYS:
            errors.append(
                f"EXPORT_POLICY[{sensitivity}] keys must be exactly "
                f"{sorted(REQUIRED_POLICY_KEYS)} (got {sorted(rule_keys)})"
            )

    restricted = policy["restricted"]
    if restricted["redact_content"] is not True:
        errors.append("restricted policy must redact content")
    if restricted["allow_tags"] is not False:
        errors.append("restricted policy must not allow tags")
    if restricted["allow_match_key"] is not False:
        errors.append("restricted policy must not allow match_key")

    public = policy["public"]
    if public["redact_content"] is not False:
        errors.append("public policy must not redact content")

    if 'if role == "admin":' not in text or "return record" not in text:
        errors.append("_export_record must keep admin bypass behavior explicit")
    if 'EXPORT_POLICY["restricted"]' not in text:
        errors.append("_export_record must fallback to restricted policy for unknown sensitivity")
    if 'exported["owner"] = "[REDACTED]"' not in text:
        errors.append("_export_record must redact owner")
    if 'exported["relations"] = {}' not in text:
        errors.append("_export_record must clear relations")
    if 'exported["obsidian_ref"] = None' not in text:
        errors.append("_export_record must clear obsidian_ref")
    if 'exported["custom_fields"] = {}' not in text:
        errors.append("_export_record must clear custom_fields")
    if 'exported["content_hash"] = ""' not in text:
        errors.append("_export_record must clear content_hash")
    if 'exported["tenant_id"] = None' not in text:
        errors.append("_export_record must clear tenant_id")

    return errors


def main() -> int:
    source = _load_source(CRUD_COMMON)
    errors = _check_export_policy_semantics(source)
    if errors:
        for err in errors:
            _fail(err)
        return 1
    print("Export contract guardrail passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
