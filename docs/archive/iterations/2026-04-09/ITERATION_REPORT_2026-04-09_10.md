# Iteration Report — 2026-04-09 (10)

- stream: contract consistency / capabilities metadata parity
- status: fixed

## Problem

Capabilities metadata loader logic is duplicated in HTTP and gateway modules, but there was no dedicated parity guardrail for `api_version`/`schema_changelog` loader semantics.

## Evidence

- `unified/src/capabilities_metadata.py` and `unified/mcp-gateway/src/capabilities_metadata.py` are parallel implementations.
- Existing guardrail coverage had manifest parity and truthfulness checks, but not metadata loader parity.

## Decision

- Added static metadata parity guardrail:
  - `scripts/check_capabilities_metadata_parity.py`
- Wired guardrail into:
  - `scripts/check_local_guardrails.py`
  - `scripts/check_pr_readiness.py` guardrail-runner tests
- Added dedicated tests and updated runner assertions/docs.

## Risk

- Low: static checks only.
- Positive: prevents silent drift in metadata validation semantics between transports.

## Validation

- `unified/.venv/bin/pytest -q unified/tests/test_capabilities_metadata_parity_guardrail.py unified/tests/test_local_guardrails_runner.py`
- `python3 scripts/check_capabilities_metadata_parity.py`
- `make pr-readiness`

## Files

- `scripts/check_capabilities_metadata_parity.py`
- `scripts/check_local_guardrails.py`
- `scripts/check_pr_readiness.py`
- `unified/tests/test_capabilities_metadata_parity_guardrail.py`
- `unified/tests/test_local_guardrails_runner.py`
- `docs/operating-manual.md`
