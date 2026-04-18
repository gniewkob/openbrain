#!/usr/bin/env python3
"""
Guardrail: validate contracts/memory_paths.json against registered FastAPI routes.

Usage:
    python scripts/check_memory_paths.py

Exits with code 0 if all paths in memory_paths.json are registered.
Exits with code 1 if any path is missing, with details written to stderr.

Designed to run in CI (no live server required — reads routes from the app object).
"""

import json
import sys
from pathlib import Path

# Locate project root (this script lives in <root>/scripts/)
_ROOT = Path(__file__).resolve().parent.parent

sys.path.insert(0, str(_ROOT))

from src.main import app  # noqa: E402 — path manipulation above; imports main which registers all routers


def _collect_routes(app) -> set[str]:
    """Return the set of all route paths registered on *app* (and its sub-apps)."""
    routes: set[str] = set()
    for route in app.routes:
        if hasattr(route, "path"):
            routes.add(route.path)
    return routes


def main() -> int:
    contract_path = _ROOT / "contracts" / "memory_paths.json"
    if not contract_path.exists():
        print(f"ERROR: contract file not found: {contract_path}", file=sys.stderr)
        return 1

    contract = json.loads(contract_path.read_text())
    memory_base: str = contract["memory_base"]
    paths: dict[str, str] = contract["paths"]

    # `app` is already fully wired with routers (imported from src.main)
    registered = _collect_routes(app)

    missing: list[str] = []
    for name, suffix in paths.items():
        full_path = memory_base + suffix
        if full_path not in registered:
            missing.append(f"  {name!r}: {full_path!r}")

    if missing:
        print("FAIL: the following paths in memory_paths.json are NOT registered:", file=sys.stderr)
        for line in missing:
            print(line, file=sys.stderr)
        print(
            "\nUpdate contracts/memory_paths.json or the router to fix the drift.",
            file=sys.stderr,
        )
        return 1

    print(f"OK: all {len(paths)} paths verified against FastAPI routes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
