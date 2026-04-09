# Iteration Report — 2026-04-09 (08)

- stream: governance / export contract guardrails
- status: fixed

## Problem

Export policy behavior was covered by unit tests, but there was no dedicated static guardrail in the local/CI guardrail bundle to fail fast on policy-contract drift.

## Evidence

- `check_local_guardrails.py` did not include an export-specific contract check.
- `check_pr_readiness.py` guardrail test set did not include export guardrail runner coverage.

## Decision

- Added new guardrail script: `scripts/check_export_contract.py` (AST-based, no runtime DB deps).
- Wired it into:
  - `scripts/check_local_guardrails.py`,
  - `scripts/check_pr_readiness.py` guardrail test suite.
- Added dedicated guardrail tests and operating manual updates.

## Risk

- Low: static checks only.
- Intentional strictness increase for export policy drift detection.

## Validation

- `unified/.venv/bin/pytest -q unified/tests/test_export_contract_guardrail.py unified/tests/test_local_guardrails_runner.py`
- `make pr-readiness`

## Files

- `scripts/check_export_contract.py`
- `scripts/check_local_guardrails.py`
- `scripts/check_pr_readiness.py`
- `unified/tests/test_export_contract_guardrail.py`
- `unified/tests/test_local_guardrails_runner.py`
- `docs/operating-manual.md`
