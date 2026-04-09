# Iteration Report — 2026-04-09 (04)

- stream: observability / guardrail robustness
- status: fixed

## Problem

Monitoring contract parser for Prometheus alert rules handled only single-line `expr:` values. Multi-line YAML expressions (`expr: |` / `expr: >`) could be skipped, creating a guardrail blind spot.

## Evidence

- `load_alert_rule_exprs` used line-by-line `startswith("expr:")` extraction with no block handling.
- Validator could miss metrics referenced in multi-line alert expressions.

## Decision

- Extended alert-rule expression parser to support block scalar expressions.
- Added regression test covering multi-line alert expression parsing.

## Risk

- Low: static parser behavior only.
- Known limitation: parser expects `expr` body to remain under greater indentation than the `expr:` line (matches current alert style).

## Validation

- `unified/.venv/bin/pytest -q unified/tests/test_monitoring_contract_guardrail.py`
- `python3 scripts/validate_monitoring_contract.py`
- `make pr-readiness`

## Files

- `scripts/validate_monitoring_contract.py`
- `unified/tests/test_monitoring_contract_guardrail.py`
