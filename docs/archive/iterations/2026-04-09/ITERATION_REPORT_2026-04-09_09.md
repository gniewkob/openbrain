# Iteration Report — 2026-04-09 (09)

- stream: contract consistency / capabilities manifest parity
- status: fixed

## Problem

Capabilities manifest loader logic exists in both HTTP transport and stdio gateway modules. There was no dedicated guardrail to detect drift between those implementations.

## Evidence

- `unified/src/capabilities_manifest.py` and `unified/mcp-gateway/src/capabilities_manifest.py` are parallel modules with duplicated invariants.
- Local/CI guardrail bundle had no explicit parity check for this pair.

## Decision

- Added static parity guardrail:
  - `scripts/check_capabilities_manifest_parity.py`
- Wired guardrail into:
  - `scripts/check_local_guardrails.py`
  - `scripts/check_pr_readiness.py` guardrail-runner test set
- Added dedicated guardrail tests and runner-step assertions.

## Risk

- Low: static check only.
- Positive: earlier failure on manifest contract drift before runtime/tool exposure.

## Validation

- `unified/.venv/bin/pytest -q unified/tests/test_capabilities_manifest_parity_guardrail.py unified/tests/test_local_guardrails_runner.py`
- `python3 scripts/check_capabilities_manifest_parity.py`
- `make pr-readiness`

## Files

- `scripts/check_capabilities_manifest_parity.py`
- `scripts/check_local_guardrails.py`
- `scripts/check_pr_readiness.py`
- `unified/tests/test_capabilities_manifest_parity_guardrail.py`
- `unified/tests/test_local_guardrails_runner.py`
- `docs/operating-manual.md`
