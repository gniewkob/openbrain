#!/usr/bin/env python3
"""Run local static guardrails in a single, deterministic sequence."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
CONTRACT = ROOT / "unified/contracts/local_guardrails_runner_contract.json"


def _load_contract() -> tuple[tuple[tuple[str, str], ...], dict[str, int]]:
    payload = json.loads(CONTRACT.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("local guardrails runner contract must be a JSON object")
    steps = payload.get("steps")
    if not isinstance(steps, list) or not steps:
        raise ValueError("contract steps must be a non-empty list")

    normalized_steps: list[tuple[str, str]] = []
    timeouts: dict[str, int] = {}
    seen_labels: set[str] = set()
    for item in steps:
        if not isinstance(item, dict):
            raise ValueError("contract steps items must be objects")
        label = item.get("label")
        script = item.get("script")
        timeout = item.get("timeout_seconds")
        if not isinstance(label, str) or not label:
            raise ValueError("contract step.label must be non-empty string")
        if not isinstance(script, str) or not script:
            raise ValueError("contract step.script must be non-empty string")
        if not isinstance(timeout, int) or timeout <= 0:
            raise ValueError("contract step.timeout_seconds must be positive int")
        if label in seen_labels:
            raise ValueError(f"contract has duplicate step label: {label}")
        seen_labels.add(label)
        normalized_steps.append((label, script))
        timeouts[label] = timeout

    return tuple(normalized_steps), timeouts


GUARDRAIL_STEPS, STEP_TIMEOUT_SECONDS = _load_contract()


def run_step(label: str, rel_script: str) -> int:
    script = ROOT / rel_script
    timeout_s = STEP_TIMEOUT_SECONDS[label]
    try:
        proc = subprocess.run(
            [sys.executable, str(script)],
            cwd=str(ROOT),
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
    except subprocess.TimeoutExpired:
        print(f"[FAIL] {label}: timed out after {timeout_s}s", file=sys.stderr)
        return 124
    if proc.stdout.strip():
        print(proc.stdout.strip())
    if proc.returncode != 0:
        stderr = proc.stderr.strip() or f"{label} guardrail failed"
        print(f"[FAIL] {label}: {stderr}", file=sys.stderr)
        return proc.returncode
    print(f"[OK] {label}")
    return 0


def main() -> int:
    for label, script in GUARDRAIL_STEPS:
        rc = run_step(label, script)
        if rc != 0:
            return rc
    print("Local guardrails bundle passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
