# Iteration Report — 2026-04-09 (11)

- stream: contract consistency / request-runtime parity
- status: fixed

## Problem

`request_contracts` and `runtime_limits` loaders are duplicated across HTTP transport and stdio gateway, but there was no dedicated parity guardrail to prevent semantic drift.

## Evidence

- `unified/src/request_builders.py` and `unified/mcp-gateway/src/request_builders.py` both define `_validate_request_contracts` and `_load_request_contracts`.
- `unified/src/runtime_limits.py` and `unified/mcp-gateway/src/runtime_limits.py` both define `_DEFAULTS`, `_validate_runtime_limits`, and `load_runtime_limits`.
- Existing parity guardrails covered capabilities manifest/metadata only.

## Decision

- Added static parity guardrail:
  - `scripts/check_request_runtime_parity.py`
- Wired guardrail into:
  - `scripts/check_local_guardrails.py`
  - `scripts/check_pr_readiness.py` guardrail-runner tests
- Added dedicated tests and updated runner assertions/docs.

## Risk

- Low: static checks only.
- Positive: catches cross-transport contract drift earlier in CI/local readiness checks.

## Validation

- `unified/.venv/bin/pytest -q unified/tests/test_request_runtime_parity_guardrail.py unified/tests/test_local_guardrails_runner.py`
- `python3 scripts/check_request_runtime_parity.py`
- `make pr-readiness`

## Files

- `scripts/check_request_runtime_parity.py`
- `scripts/check_local_guardrails.py`
- `scripts/check_pr_readiness.py`
- `unified/tests/test_request_runtime_parity_guardrail.py`
- `unified/tests/test_local_guardrails_runner.py`
- `docs/operating-manual.md`
