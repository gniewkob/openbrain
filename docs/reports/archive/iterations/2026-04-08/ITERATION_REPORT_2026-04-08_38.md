# Iteration Report 38 (2026-04-08)

## Problem

`brain_capabilities` still exposed only coarse backend status, which made it hard to
separate true outage from partial degradation at component level.

## Evidence

- Existing payload had `backend.status`, `api`, `db`, `vector_store` but no normalized,
  contract-guarded component health summary.
- Operator feedback emphasized mismatch risk between “backend unavailable” messaging and
  partially functioning runtime paths.

## Decision

- Added `health` object to capabilities response in both transports:
  - `health.overall`
  - `health.source`
  - `health.components.{api,db,vector_store,obsidian}`
- Kept existing `backend` structure for backward compatibility.
- Extended shared response contract and tests to enforce new fields.
- Bumped capabilities metadata version to `2.3.0`.

## Validation

- `pytest -q unified/tests/test_capabilities_response_contract.py unified/tests/test_mcp_transport.py unified/tests/test_transport_parity.py unified/tests/test_contract_integrity.py` -> pass.
- `python -m unittest tests.test_capabilities_response_contract tests.test_gateway_contract_integrity tests.test_obsidian_tools -v` (from `unified/mcp-gateway`) -> pass.
- `python3 scripts/check_repo_hygiene.py` -> pass.

## Risk

- Low-to-medium: consumers that strictly validate exact payload shape (instead of allowing
  additive fields) may need adjustment.

## Status

`fixed`

