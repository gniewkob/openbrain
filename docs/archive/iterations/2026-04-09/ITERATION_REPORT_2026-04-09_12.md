# Iteration Report — 2026-04-09 (12)

- stream: observability / health truthfulness parity
- status: fixed

## Problem

`capabilities_health` logic is duplicated across HTTP transport and stdio gateway, but there was no dedicated parity guardrail for `_api_component`, `_store_component`, and `build_capabilities_health`.

## Evidence

- `unified/src/capabilities_health.py` and `unified/mcp-gateway/src/capabilities_health.py` are parallel implementations.
- Existing checks validated health payload presence and fallback probe semantics, but not strict function-level parity.

## Decision

- Added static parity guardrail:
  - `scripts/check_capabilities_health_parity.py`
- Wired guardrail into:
  - `scripts/check_local_guardrails.py`
  - `scripts/check_pr_readiness.py` guardrail-runner tests
- Added dedicated tests and updated runner assertions/docs.

## Risk

- Low: static checks only.
- Positive: reduces risk of silent drift in cross-transport `health.overall` semantics.

## Validation

- `unified/.venv/bin/pytest -q unified/tests/test_capabilities_health_parity_guardrail.py unified/tests/test_local_guardrails_runner.py`
- `python3 scripts/check_capabilities_health_parity.py`
- `make pr-readiness`

## Files

- `scripts/check_capabilities_health_parity.py`
- `scripts/check_local_guardrails.py`
- `scripts/check_pr_readiness.py`
- `unified/tests/test_capabilities_health_parity_guardrail.py`
- `unified/tests/test_local_guardrails_runner.py`
- `docs/operating-manual.md`
