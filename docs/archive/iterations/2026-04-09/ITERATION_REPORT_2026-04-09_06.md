# Iteration Report — 2026-04-09 (06)

- stream: observability / monitoring guardrail test depth
- status: fixed

## Problem

Monitoring contract guardrail gained alert-rule coverage, but regression tests did not explicitly cover:
- `vector(0)` rejection in alert rules,
- missing `alert_rule_files` path handling.

## Evidence

- Existing tests validated dashboard mismatch and basic alert-rule token extraction.
- No dedicated test ensured vector-zero policy or missing file error semantics for alert rules.

## Decision

- Added focused guardrail tests for:
  - forbidden `vector(0)` in alert rule expressions,
  - missing alert-rule file detection.

## Risk

- Very low: test-only change.
- Improves failure specificity when monitoring contract regresses.

## Validation

- `unified/.venv/bin/pytest -q unified/tests/test_monitoring_contract_guardrail.py`
- `make pr-readiness`

## Files

- `unified/tests/test_monitoring_contract_guardrail.py`
