#!/usr/bin/env python3
"""Fail CI if docker-compose.unified.yml regresses on security-sensitive guardrails."""

from __future__ import annotations

from pathlib import Path
import sys


COMPOSE_PATH = Path(__file__).resolve().parents[1] / "docker-compose.unified.yml"


def main() -> int:
    content = COMPOSE_PATH.read_text(encoding="utf-8")

    # We now require variables to be provided by the environment (e.g. via start_unified.sh)
    # to avoid hardcoding even default "postgres" strings which trigger GitGuardian.
    required_snippets = [
        'POSTGRES_USER: ${POSTGRES_USER}',
        'POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}',
        'POSTGRES_DB: ${POSTGRES_DB}',
        'pg_isready -U ${POSTGRES_USER} -d ${POSTGRES_DB}',
        'postgresql+asyncpg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@db:5432/${POSTGRES_DB}',
    ]

    missing = [snippet for snippet in required_snippets if snippet not in content]
    if missing:
        print("docker-compose.unified.yml is missing expected guardrail snippets:", file=sys.stderr)
        for snippet in missing:
            print(f"  - {snippet}", file=sys.stderr)
        return 1

    forbidden_snippets = [
        'pg_isready -U postgres',
        'postgresql+asyncpg://postgres:postgres',
        ':-postgres',
        ':-admin',
    ]

    present_forbidden = [snippet for snippet in forbidden_snippets if snippet in content]
    if present_forbidden:
        print("docker-compose.unified.yml still contains hardcoded dev credentials or defaults:", file=sys.stderr)
        for snippet in present_forbidden:
            print(f"  - {snippet}", file=sys.stderr)
        return 1

    print("compose guardrails ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
