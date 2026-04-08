# Iteration Report 39 (2026-04-08)

## Problem

`brain_capabilities` could still report full outage when `/readyz` and `/healthz`
failed, even if core API remained reachable. This was a direct truthfulness risk.

## Evidence

- Status probe sequence previously ended with `unavailable` after two failed probes.
- Original user report indicated runtime operations could work despite health mismatch.

## Decision

- Added third fallback probe to `GET /api/v1/health` in both transports:
  - if reachable -> report `backend.status=degraded`, `probe=api_health_fallback`
  - if unreachable -> keep `backend.status=unavailable`
- Added tests for this scenario in both transports.
- Renamed gateway contract test file to avoid confusing duplicate naming and updated
  CI workflow patterns.

## Validation

- `pytest -q unified/tests/test_mcp_transport.py unified/tests/test_capabilities_response_contract.py unified/tests/test_transport_parity.py unified/tests/test_contract_integrity.py` -> pass.
- `python -m unittest tests.test_obsidian_tools tests.test_gateway_capabilities_response_contract tests.test_gateway_contract_integrity -v` (from `unified/mcp-gateway`) -> pass.
- `python3 scripts/check_repo_hygiene.py` -> pass.

## Risk

- Low: additive fallback behavior.
- Medium: one more probe path increases code-path complexity, covered by tests.

## Status

`fixed`

