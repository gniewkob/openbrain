#!/usr/bin/env python3
"""Run a minimal, deterministic local PR-readiness bundle."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
PREFERRED_TEST_PYTHON = ROOT / ".venv" / "bin" / "python"
CONTRACT = ROOT / "unified/contracts/pr_readiness_runner_contract.json"


def _test_python() -> str:
    if PREFERRED_TEST_PYTHON.exists():
        return str(PREFERRED_TEST_PYTHON)
    return sys.executable

def _load_contract() -> tuple[list[str], list[str], dict[str, int]]:
    payload = json.loads(CONTRACT.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("pr_readiness_runner_contract must be a JSON object")

    def _require_string_list(field_name: str) -> list[str]:
        value = payload.get(field_name)
        if not isinstance(value, list) or not value:
            raise ValueError(f"contract {field_name} must be non-empty list")
        if any(not isinstance(item, str) or not item for item in value):
            raise ValueError(f"contract {field_name} must contain non-empty strings")
        return [str(item) for item in value]

    guardrail_tests = _require_string_list("guardrail_runner_test_files")
    contract_smoke_tests = _require_string_list("contract_integrity_test_files")

    timeouts_raw = payload.get("step_timeouts_seconds")
    if not isinstance(timeouts_raw, dict) or not timeouts_raw:
        raise ValueError("contract step_timeouts_seconds must be non-empty object")

    required_labels = {
        "local guardrails",
        "guardrail runner tests",
        "contract integrity smoke",
    }
    missing_labels = sorted(required_labels - set(timeouts_raw.keys()))
    if missing_labels:
        raise ValueError(f"contract step_timeouts_seconds missing labels: {missing_labels}")

    timeouts: dict[str, int] = {}
    for label, raw_timeout in timeouts_raw.items():
        if not isinstance(label, str) or not label:
            raise ValueError("contract step_timeouts_seconds keys must be non-empty strings")
        if not isinstance(raw_timeout, int) or raw_timeout <= 0:
            raise ValueError("contract step_timeouts_seconds values must be positive ints")
        timeouts[label] = raw_timeout

    return guardrail_tests, contract_smoke_tests, timeouts


_GUARDRAIL_TESTS, _CONTRACT_SMOKE_TESTS, STEP_TIMEOUT_SECONDS = _load_contract()

PR_READINESS_STEPS: tuple[tuple[str, list[str]], ...] = (
    ("local guardrails", [sys.executable, "scripts/check_local_guardrails.py"]),
    (
        "guardrail runner tests",
        [_test_python(), "-m", "pytest", "-q", *_GUARDRAIL_TESTS],
    ),
    (
        "contract integrity smoke",
        [_test_python(), "-m", "pytest", "-q", *_CONTRACT_SMOKE_TESTS],
    ),
)


def run_step(label: str, cmd: list[str]) -> int:
    timeout_s = STEP_TIMEOUT_SECONDS.get(label, 300)
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(ROOT),
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
    except subprocess.TimeoutExpired:
        print(
            f"[FAIL] {label}: timed out after {timeout_s}s",
            file=sys.stderr,
        )
        return 124
    if proc.stdout.strip():
        print(proc.stdout.strip())
    if proc.returncode != 0:
        stderr = proc.stderr.strip() or f"{label} failed"
        print(f"[FAIL] {label}: {stderr}", file=sys.stderr)
        return proc.returncode
    print(f"[OK] {label}")
    return 0


def main() -> int:
    for label, cmd in PR_READINESS_STEPS:
        rc = run_step(label, cmd)
        if rc != 0:
            return rc
    print("PR readiness bundle passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
