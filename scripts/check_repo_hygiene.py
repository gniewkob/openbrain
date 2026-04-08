#!/usr/bin/env python3
"""Basic repository hygiene guardrails for known debug artifacts."""

from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parent.parent

# Explicit deny-list for ad-hoc debug artifacts that must not return.
FORBIDDEN_PATHS = (
    "reproduce_hang.py",
)


def main() -> int:
    violations: list[str] = []
    for rel in FORBIDDEN_PATHS:
        path = ROOT / rel
        if path.exists():
            violations.append(rel)

    if violations:
        print("Repository hygiene check failed; forbidden artifacts found:", file=sys.stderr)
        for rel in violations:
            print(f"- {rel}", file=sys.stderr)
        return 1

    print("Repository hygiene check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
