#!/usr/bin/env python3
"""Fail CI if docker-compose.unified.yml regresses on security-sensitive guardrails."""

from __future__ import annotations

import json
from pathlib import Path
import sys


COMPOSE_PATH = Path(__file__).resolve().parents[1] / "docker-compose.unified.yml"
CONTRACT_PATH = Path(__file__).resolve().parents[1] / "unified/contracts/compose_guardrails_contract.json"


def _validate_snippet_list(value: object, field_name: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"contract {field_name} must be non-empty list")
    if any(not isinstance(item, str) or not item for item in value):
        raise ValueError(f"contract {field_name} must contain non-empty strings")
    return [str(item) for item in value]


def load_contract() -> dict[str, list[str]]:
    payload = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("compose guardrails contract must be an object")
    return {
        "required_snippets": _validate_snippet_list(
            payload.get("required_snippets"), "required_snippets"
        ),
        "forbidden_snippets": _validate_snippet_list(
            payload.get("forbidden_snippets"), "forbidden_snippets"
        ),
        "required_public_transport_snippets": _validate_snippet_list(
            payload.get("required_public_transport_snippets"),
            "required_public_transport_snippets",
        ),
    }


def find_missing_required_snippets(content: str, required_snippets: list[str]) -> list[str]:
    return [snippet for snippet in required_snippets if snippet not in content]


def find_forbidden_snippets(content: str, forbidden_snippets: list[str]) -> list[str]:
    return [snippet for snippet in forbidden_snippets if snippet in content]


def find_missing_public_transport_snippets(
    content: str, required_snippets: list[str]
) -> list[str]:
    return [snippet for snippet in required_snippets if snippet not in content]


def main() -> int:
    content = COMPOSE_PATH.read_text(encoding="utf-8")
    contract = load_contract()

    # Variables must be provided by the environment (e.g. via start_unified.sh)
    # so shared/public runs cannot silently inherit compose-level credential defaults.
    missing = find_missing_required_snippets(content, contract["required_snippets"])
    if missing:
        print("docker-compose.unified.yml is missing expected guardrail snippets:", file=sys.stderr)
        for snippet in missing:
            print(f"  - {snippet}", file=sys.stderr)
        return 1

    present_forbidden = find_forbidden_snippets(content, contract["forbidden_snippets"])
    if present_forbidden:
        print("docker-compose.unified.yml still contains hardcoded dev credentials or defaults:", file=sys.stderr)
        for snippet in present_forbidden:
            print(f"  - {snippet}", file=sys.stderr)
        return 1

    missing_public_transport = find_missing_public_transport_snippets(
        content, contract["required_public_transport_snippets"]
    )
    if missing_public_transport:
        print(
            "docker-compose.unified.yml is missing public transport safety snippets:",
            file=sys.stderr,
        )
        for snippet in missing_public_transport:
            print(f"  - {snippet}", file=sys.stderr)
        return 1

    print("compose guardrails ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
