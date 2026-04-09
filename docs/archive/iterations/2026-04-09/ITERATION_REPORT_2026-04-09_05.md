# Iteration Report — 2026-04-09 (05)

- stream: observability / capabilities truthfulness guardrail hardening
- status: fixed

## Problem

Capabilities truthfulness guardrail validated only the final API health fallback marker. It did not enforce the full fallback chain (`/readyz` -> `/healthz` -> `/api/v1/health`) or presence of `readyz_status_code`.

## Evidence

- `scripts/check_capabilities_truthfulness.py` checked only:
  - `api_health_fallback`
  - `/api/v1/health`
- Missing checks allowed potential drift in primary/secondary probe semantics without guardrail failure.

## Decision

- Extended guardrail static checks to require:
  - `/readyz` + `readyz` marker,
  - `/healthz` + `healthz_fallback` marker,
  - `readyz_status_code` key,
  - existing `/api/v1/health` + `api_health_fallback` checks.
- Updated guardrail unit test fixtures for new invariants.

## Risk

- Low: static checks only, no runtime behavior change.
- Positive strictness increase: future probe refactors now require explicit contract updates.

## Validation

- `unified/.venv/bin/pytest -q unified/tests/test_capabilities_truthfulness_guardrail.py`
- `make pr-readiness`

## Files

- `scripts/check_capabilities_truthfulness.py`
- `unified/tests/test_capabilities_truthfulness_guardrail.py`
