#!/usr/bin/env python3
"""Fail CI if docker-compose.unified.yml regresses on security-sensitive guardrails."""

from __future__ import annotations

from pathlib import Path
import sys


COMPOSE_PATH = Path(__file__).resolve().parents[1] / "docker-compose.unified.yml"


def main() -> int:
    content = COMPOSE_PATH.read_text(encoding="utf-8")

    required_snippets = [
        'POSTGRES_USER: ${POSTGRES_USER:-postgres}',
        'POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-postgres}',
        'POSTGRES_DB: ${POSTGRES_DB:-openbrain_unified}',
        'pg_isready -U ${POSTGRES_USER:-postgres} -d ${POSTGRES_DB:-openbrain_unified}',
        'postgresql+asyncpg://${POSTGRES_USER:-postgres}:${POSTGRES_PASSWORD:-postgres}@db:5432/${POSTGRES_DB:-openbrain_unified}',
    ]

    missing = [snippet for snippet in required_snippets if snippet not in content]
    if missing:
        print("docker-compose.unified.yml is missing expected guardrail snippets:", file=sys.stderr)
        for snippet in missing:
            print(f"  - {snippet}", file=sys.stderr)
        return 1

    forbidden_snippets = [
        'pg_isready -U postgres -d openbrain_unified',
        'postgresql+asyncpg://postgres:postgres@db:5432/openbrain_unified',
    ]

    present_forbidden = [snippet for snippet in forbidden_snippets if snippet in content]
    if present_forbidden:
        print("docker-compose.unified.yml still contains hardcoded dev credentials:", file=sys.stderr)
        for snippet in present_forbidden:
            print(f"  - {snippet}", file=sys.stderr)
        return 1

    print("compose guardrails ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
