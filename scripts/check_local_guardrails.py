#!/usr/bin/env python3
"""Run local static guardrails in a single, deterministic sequence."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent

GUARDRAIL_STEPS: tuple[tuple[str, str], ...] = (
    ("repository hygiene", "scripts/check_repo_hygiene.py"),
    ("compose guardrails", "scripts/check_compose_guardrails.py"),
    ("capabilities manifest parity", "scripts/check_capabilities_manifest_parity.py"),
    ("capabilities metadata parity", "scripts/check_capabilities_metadata_parity.py"),
    ("capabilities health parity", "scripts/check_capabilities_health_parity.py"),
    ("request/runtime parity", "scripts/check_request_runtime_parity.py"),
    ("response normalizers parity", "scripts/check_response_normalizers_parity.py"),
    ("capabilities truthfulness", "scripts/check_capabilities_truthfulness.py"),
    ("audit semantics", "scripts/check_audit_semantics.py"),
    ("delete semantics parity", "scripts/check_delete_semantics_parity.py"),
    ("export contract", "scripts/check_export_contract.py"),
    ("obsidian contract", "scripts/check_obsidian_contract.py"),
    ("mcp http session contract", "scripts/check_mcp_http_session_contract.py"),
    ("monitoring contract", "scripts/validate_monitoring_contract.py"),
)


def run_step(label: str, rel_script: str) -> int:
    script = ROOT / rel_script
    proc = subprocess.run(
        [sys.executable, str(script)],
        cwd=str(ROOT),
        check=False,
        capture_output=True,
        text=True,
    )
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
