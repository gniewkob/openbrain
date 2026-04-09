# Iteration Report — 2026-04-09 (07)

- stream: governance / export semantics regression coverage
- status: fixed

## Problem

Export policy tests covered `internal` and `confidential`, but did not explicitly lock behavior for:
- `restricted` sensitivity,
- unknown sensitivity fallback behavior,
- current admin bypass semantics for restricted records.

## Evidence

- `unified/tests/test_export_policy.py` lacked dedicated test cases for those scenarios.
- `crud_common._export_record` has explicit fallback to `restricted` policy and role-based bypass for `admin`.

## Decision

- Added regression tests for:
  - strict redaction of `restricted` records,
  - fallback-to-restricted behavior for unknown sensitivity values,
  - current admin bypass behavior on restricted records (explicitly documented as current contract).

## Risk

- Low: test-only change.
- Positive effect: prevents silent governance drift in export behavior.

## Validation

- `unified/.venv/bin/pytest -q unified/tests/test_export_policy.py`
- `make pr-readiness`

## Files

- `unified/tests/test_export_policy.py`
