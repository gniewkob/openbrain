# Iteration Report — 2026-04-09 (03)

- stream: observability / monitoring contract integrity
- status: fixed

## Problem

Monitoring contract validation only checked Grafana dashboard expressions. Prometheus alert rules could drift outside declared `required_metrics` without guardrail failure.

## Evidence

- `scripts/validate_monitoring_contract.py` only loaded `dashboard_files`.
- Contract schema had no `alert_rule_files` input.
- Alert expressions in `monitoring/prometheus/openbrain-alerts.yml` were not contract-validated.

## Decision

- Extended contract validator to parse `expr:` from alert/record rules in Prometheus YAML.
- Added `alert_rule_files` to monitoring contract and wired current OpenBrain alert rules path.
- Unified mismatch error message to cover all monitoring expressions.
- Updated guardrail tests and operating manual wording.

## Risk

- Low: static validation scope increase only.
- Minor parser limitation: alert expression parser is line-based (`expr:` single-line), matching current repo style.

## Validation

- `unified/.venv/bin/pytest -q unified/tests/test_monitoring_contract_guardrail.py`
- `python3 scripts/validate_monitoring_contract.py`
- `make pr-readiness`

## Files

- `scripts/validate_monitoring_contract.py`
- `unified/tests/test_monitoring_contract_guardrail.py`
- `monitoring/contracts/openbrain-metrics-contract.json`
- `docs/operating-manual.md`
