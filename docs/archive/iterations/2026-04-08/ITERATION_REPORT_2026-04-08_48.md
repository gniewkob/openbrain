# Iteration Report 48 (2026-04-08)

## Stream
- CI governance hardening (external security gate unblock)

## Problem
- PR remained blocked by `GitGuardian Security Checks` despite runtime and contract checks passing.
- Findings pointed to secret-like literals in historical commits of `.github/workflows/ci-enhanced.yml`.

## Evidence
- `gh pr checks 1` reported `GitGuardian Security Checks: fail`.
- GitGuardian findings referenced historical commits in the PR range where workflow contained:
  - `POSTGRES_PASSWORD: postgres`
  - password-bearing connection-string forms.

## Decision
- Keep Postgres service auth in CI without explicit password literal:
  - `POSTGRES_HOST_AUTH_METHOD: trust`
  - `DATABASE_URL` without password fragment.
- Rewrite branch history for the two offending commits so flagged literals are removed from commit range scanned by GitGuardian.
- Force-push with lease to update only the PR branch.

## Changes
- Workflow sanitization:
  - `.github/workflows/ci-enhanced.yml`
- Branch history rewrite:
  - edited commits formerly rooted at `ea8b82f` and `55165dc` (new SHAs after rebase).

## Validation
- Local governance checks:
  - `python3 scripts/check_pr_readiness.py` -> pass
  - `python3 scripts/check_release_gate.py` -> pass
- PR checks:
  - `gh pr checks 1` -> all internal checks pass
  - `GitGuardian Security Checks` -> pass

## Risk
- Branch history rewrite changes commit SHAs and requires collaborators to resync local branch.
- CI Postgres trust mode is scoped to ephemeral GitHub Actions service and not production runtime.

## Status
- `fixed` — external gate blocker removed; PR checkset is now fully green.
