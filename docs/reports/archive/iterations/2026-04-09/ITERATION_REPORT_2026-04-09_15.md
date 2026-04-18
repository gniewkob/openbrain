# Iteration Report — 2026-04-09 (15)

- stream: observability / capabilities truthfulness guardrail resilience
- status: fixed

## Problem

`check_capabilities_truthfulness.py` hardcoded `api_version == 2.3.0`, which would create false guardrail failures on legitimate version bumps.

## Evidence

- `_check_metadata` required exact string `2.3.0`.
- Metadata contract already carries dynamic `api_version` + `schema_changelog`; static pinning is unnecessary and brittle.

## Decision

- Replaced static version pinning with dynamic contract checks:
  - `api_version` must match `MAJOR.MINOR.PATCH`
  - `schema_changelog` must be an object and contain current `api_version`
  - changelog must contain at least one health semantics entry
- Added regression tests for dynamic version acceptance and missing-health-entry failure mode.

## Risk

- Low: guardrail logic only.
- Positive: reduces false positives while keeping truthfulness intent enforced.

## Validation

- `unified/.venv/bin/pytest -q unified/tests/test_capabilities_truthfulness_guardrail.py`
- `python3 scripts/check_capabilities_truthfulness.py`
- `make pr-readiness`

## Files

- `scripts/check_capabilities_truthfulness.py`
- `unified/tests/test_capabilities_truthfulness_guardrail.py`
- `docs/archive/iterations/2026-04-09/ITERATION_REPORT_2026-04-09_15.md`
