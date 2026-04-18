# Iteration Report 40 (2026-04-08)

## Problem

After introducing richer health semantics, there was no dedicated guardrail in the
`guardrails` CI job that would fail fast on future status-truthfulness regressions.

## Evidence

- `guardrails` already enforced release gate and hygiene, but not capabilities
  status invariants.
- Regression risk remained if someone removed `health` payload or probe fallback
  logic without touching unit-test scope executed in this job.

## Decision

- Added policy script: `scripts/check_capabilities_truthfulness.py`.
- Script enforces:
  - `health` contract keys in `capabilities_response_contract.json`,
  - metadata version/changelog coherence in `capabilities_metadata.json`,
  - required source invariants in both transports:
    - `health` object in response payload,
    - `/api/v1/health` fallback probe,
    - `api_health_fallback` marker.
- Wired script into `Unified Smoke Tests / guardrails`.

## Validation

- `python3 scripts/check_capabilities_truthfulness.py` -> pass.
- `pytest -q unified/tests/test_mcp_transport.py unified/tests/test_capabilities_response_contract.py unified/tests/test_contract_integrity.py` -> pass.
- `python -m unittest tests.test_gateway_capabilities_response_contract tests.test_gateway_contract_integrity tests.test_obsidian_tools -v` (from `unified/mcp-gateway`) -> pass.

## Risk

- Low: static guardrail may need update when capabilities contract intentionally evolves.

## Status

`fixed`

