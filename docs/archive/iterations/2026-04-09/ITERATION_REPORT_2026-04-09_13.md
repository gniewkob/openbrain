# Iteration Report — 2026-04-09 (13)

- stream: contract consistency / capabilities response validation
- status: fixed

## Problem

Capabilities response contract tests validated only HTTP transport shape directly; gateway-side contract adherence depended on broader transport parity coverage.

## Evidence

- `unified/tests/test_capabilities_response_contract.py` only exercised `src.mcp_transport.brain_capabilities()`.
- Gateway had parity tests, but no dedicated response-contract assertion path reusing the same contract fixture.

## Decision

- Extended capabilities response contract test suite with gateway coverage:
  - `test_gateway_capabilities_follow_response_contract_when_available`
- Gateway test is environment-aware and safely skips when gateway import dependencies are unavailable.

## Risk

- Low: test-only change.
- Positive: tighter contract guarantees for both transports in one canonical test suite.

## Validation

- `unified/.venv/bin/pytest -q unified/tests/test_capabilities_response_contract.py`
- `make pr-readiness`

## Files

- `unified/tests/test_capabilities_response_contract.py`
- `docs/archive/iterations/2026-04-09/ITERATION_REPORT_2026-04-09_13.md`
