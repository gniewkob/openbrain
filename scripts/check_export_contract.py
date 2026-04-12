#!/usr/bin/env python3
"""Guardrail: enforce export redaction contract invariants."""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
CRUD_COMMON = ROOT / "unified/src/crud_common.py"
CONTRACT = ROOT / "unified/contracts/export_guardrail_contract.json"


def _fail(message: str) -> int:
    print(f"[FAIL] {message}", file=sys.stderr)
    return 1


def _load_source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _load_contract() -> dict[str, object]:
    payload = json.loads(CONTRACT.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("export_guardrail_contract must be object")
    for key in (
        "required_sensitivities",
        "required_policy_keys",
        "required_behavior_snippets",
    ):
        value = payload.get(key)
        if not isinstance(value, list) or not value:
            raise ValueError(f"contract {key} must be non-empty list")
        if any(not isinstance(item, str) or not item for item in value):
            raise ValueError(f"contract {key} must contain non-empty strings")
    return payload


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


def _check_export_policy_semantics(
    text: str, contract: dict[str, object]
) -> list[str]:
    errors: list[str] = []
    required_sensitivities = {
        str(item) for item in contract["required_sensitivities"]
    }
    required_policy_keys = {str(item) for item in contract["required_policy_keys"]}
    required_behavior_snippets = [
        str(item) for item in contract["required_behavior_snippets"]
    ]
    try:
        policy = _extract_export_policy(text)
    except Exception as exc:
        return [f"unable to parse EXPORT_POLICY: {exc}"]

    sensitivities = set(policy.keys())
    if sensitivities != required_sensitivities:
        errors.append(
            "EXPORT_POLICY sensitivities must be exactly "
            f"{sorted(required_sensitivities)} (got {sorted(sensitivities)})"
        )
        return errors

    for sensitivity, rules in policy.items():
        rule_keys = set(rules.keys())
        if rule_keys != required_policy_keys:
            errors.append(
                f"EXPORT_POLICY[{sensitivity}] keys must be exactly "
                f"{sorted(required_policy_keys)} (got {sorted(rule_keys)})"
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

    snippet_errors = {
        'if role == "admin":': "_export_record must keep admin bypass behavior explicit",
        "return record": "_export_record must keep admin bypass behavior explicit",
        'EXPORT_POLICY["restricted"]': "_export_record must fallback to restricted policy for unknown sensitivity",
        'exported["owner"] = "[REDACTED]"': "_export_record must redact owner",
        'exported["relations"] = {}': "_export_record must clear relations",
        'exported["obsidian_ref"] = None': "_export_record must clear obsidian_ref",
        'exported["custom_fields"] = {}': "_export_record must clear custom_fields",
        'exported["content_hash"] = ""': "_export_record must clear content_hash",
        'exported["tenant_id"] = None': "_export_record must clear tenant_id",
    }
    for snippet in required_behavior_snippets:
        if snippet not in text:
            errors.append(
                snippet_errors.get(
                    snippet, f"_export_record missing required behavior snippet: {snippet}"
                )
            )

    return errors


def main() -> int:
    contract = _load_contract()
    source = _load_source(CRUD_COMMON)
    errors = _check_export_policy_semantics(source, contract)
    if errors:
        for err in errors:
            _fail(err)
        return 1
    print("Export contract guardrail passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
