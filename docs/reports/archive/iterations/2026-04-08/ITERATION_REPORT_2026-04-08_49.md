# Iteration Report 49 (2026-04-08)

## Stream
- CI quality/performance hardening

## Problem
- Legacy CI workflow (`ci.yml`) still used password-style Postgres wiring (`postgres:postgres`) that could reintroduce secret-scan false positives.
- PR pushes could run overlapping workflow instances, creating redundant CI noise and slower feedback.

## Evidence
- `.github/workflows/ci.yml` contained `DATABASE_URL` with inline password pattern.
- `Unified Smoke Tests` and `CI` workflows lacked top-level `concurrency` cancellation.

## Decision
- Standardize CI Postgres auth to password-less trust mode for ephemeral GitHub service containers.
- Add workflow-level `concurrency` to cancel superseded in-progress runs per branch/ref.

## Changes
- `.github/workflows/ci.yml`
  - Added:
    - `concurrency.group: ci-${{ github.workflow }}-${{ github.ref }}`
    - `cancel-in-progress: true`
  - Switched Postgres service env to:
    - `POSTGRES_HOST_AUTH_METHOD: trust`
  - Updated test DB URL to:
    - `postgresql+asyncpg://postgres@localhost:5432/openbrain_test`
- `.github/workflows/unified-smoke.yml`
  - Added:
    - `concurrency.group: smoke-${{ github.workflow }}-${{ github.ref }}`
    - `cancel-in-progress: true`

## Validation
- `python3 scripts/check_no_committed_secrets.py` -> pass
- `python3 scripts/check_pr_readiness.py` -> pass
- Pattern scan for password-style literals in CI workflows -> no matches

## Risk
- `concurrency` cancellation can stop older long-running jobs when a newer push arrives; this is intentional and improves signal-to-noise in PR iteration.

## Status
- `fixed` — CI workflow hygiene tightened and duplicate-run pressure reduced.
