#!/usr/bin/env python3
"""Run a minimal, deterministic local PR-readiness bundle."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
PREFERRED_TEST_PYTHON = ROOT / ".venv" / "bin" / "python"


def _test_python() -> str:
    if PREFERRED_TEST_PYTHON.exists():
        return str(PREFERRED_TEST_PYTHON)
    return sys.executable

PR_READINESS_STEPS: tuple[tuple[str, list[str]], ...] = (
    ("local guardrails", [sys.executable, "scripts/check_local_guardrails.py"]),
    (
        "guardrail runner tests",
        [
            _test_python(),
            "-m",
            "pytest",
            "-q",
            "unified/tests/test_local_guardrails_runner.py",
            "unified/tests/test_repo_hygiene_guardrail.py",
            "unified/tests/test_compose_guardrails.py",
            "unified/tests/test_secret_scan_guardrail.py",
            "unified/tests/test_capabilities_manifest_parity_guardrail.py",
            "unified/tests/test_capabilities_metadata_parity_guardrail.py",
            "unified/tests/test_capabilities_health_parity_guardrail.py",
            "unified/tests/test_request_runtime_parity_guardrail.py",
            "unified/tests/test_tool_signature_parity_guardrail.py",
            "unified/tests/test_search_filter_parity_guardrail.py",
            "unified/tests/test_response_normalizers_parity_guardrail.py",
            "unified/tests/test_capabilities_truthfulness_guardrail.py",
            "unified/tests/test_audit_semantics_guardrail.py",
            "unified/tests/test_delete_semantics_parity_guardrail.py",
            "unified/tests/test_export_contract_guardrail.py",
            "unified/tests/test_obsidian_contract_guardrail.py",
            "unified/tests/test_mcp_http_session_contract_guardrail.py",
            "unified/tests/test_monitoring_contract_guardrail.py",
        ],
    ),
    (
        "contract integrity smoke",
        [
            _test_python(),
            "-m",
            "pytest",
            "-q",
            "unified/tests/test_contract_integrity.py",
            "unified/tests/test_capabilities_response_contract.py",
        ],
    ),
)


def run_step(label: str, cmd: list[str]) -> int:
    proc = subprocess.run(
        cmd,
        cwd=str(ROOT),
        check=False,
        capture_output=True,
        text=True,
    )
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
