#!/usr/bin/env python3
"""Check GitHub branch protection and required status checks for release gate drift."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONTRACT = ROOT / "unified/contracts/release_gate_contract.json"


def _load_contract() -> tuple[str, ...]:
    payload = json.loads(CONTRACT.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("release_gate_contract must be object")
    required_checks = payload.get("required_checks")
    if not isinstance(required_checks, list) or not required_checks:
        raise ValueError("contract required_checks must be non-empty list")
    if any(not isinstance(check, str) or not check for check in required_checks):
        raise ValueError("contract required_checks must contain non-empty strings")
    return tuple(required_checks)


REQUIRED_CHECKS = _load_contract()


@dataclass(frozen=True)
class ReleaseGateStatus:
    repo: str
    branch: str
    protected: bool
    required_checks: tuple[str, ...]
    missing_checks: tuple[str, ...]

    @property
    def healthy(self) -> bool:
        return self.protected and not self.missing_checks


def _run_gh_json(args: list[str]) -> dict | list:
    proc = subprocess.run(
        ["gh", *args],
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        stderr = (proc.stderr or "").strip()
        raise RuntimeError(stderr or f"gh command failed: {' '.join(args)}")
    return json.loads(proc.stdout)


def _get_repo_and_branch() -> tuple[str, str]:
    payload = _run_gh_json(["repo", "view", "--json", "nameWithOwner,defaultBranchRef"])
    repo = payload["nameWithOwner"]
    branch = payload["defaultBranchRef"]["name"]
    return repo, branch


def _get_branch_protection(repo: str, branch: str) -> dict | None:
    proc = subprocess.run(
        ["gh", "api", f"repos/{repo}/branches/{branch}/protection"],
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode == 0:
        return json.loads(proc.stdout)
    stderr = (proc.stderr or "").lower()
    if "404" in stderr or "not found" in stderr:
        return None
    raise RuntimeError((proc.stderr or "").strip() or "unable to read branch protection")


def evaluate_release_gate() -> ReleaseGateStatus:
    repo, branch = _get_repo_and_branch()
    protection = _get_branch_protection(repo, branch)
    if protection is None:
        return ReleaseGateStatus(
            repo=repo,
            branch=branch,
            protected=False,
            required_checks=(),
            missing_checks=REQUIRED_CHECKS,
        )

    current = tuple(protection.get("required_status_checks", {}).get("contexts", []) or ())
    missing = tuple(check for check in REQUIRED_CHECKS if check not in current)
    return ReleaseGateStatus(
        repo=repo,
        branch=branch,
        protected=True,
        required_checks=current,
        missing_checks=missing,
    )


def main() -> int:
    enforce = os.getenv("RELEASE_GATE_ENFORCE", "0") == "1"
    try:
        status = evaluate_release_gate()
    except RuntimeError as err:
        err_text = str(err).lower()
        if "resource not accessible by integration" in err_text or "http 403" in err_text:
            print(f"[WARN] release-gate check skipped (insufficient token scope): {err}")
            return 0
        if enforce:
            print(f"[FAIL] release-gate check error: {err}", file=sys.stderr)
            return 2
        print(f"[WARN] release-gate check skipped: {err}")
        return 0

    print(f"repo={status.repo} branch={status.branch}")
    if not status.protected:
        print("[WARN] Branch is not protected.")
    else:
        print(f"[OK] Branch protection enabled with {len(status.required_checks)} checks.")

    if status.missing_checks:
        print("[WARN] Missing required checks:")
        for check in status.missing_checks:
            print(f"  - {check}")
    else:
        print("[OK] All required checks configured.")

    if enforce and not status.healthy:
        print(
            "[FAIL] release-gate policy violation (set RELEASE_GATE_ENFORCE=0 for audit-only mode).",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
