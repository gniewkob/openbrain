# Iteration Report — 2026-04-09 (17)

- stream: contract consistency / capabilities transport parity tests
- status: fixed

## Problem

`test_transport_parity.py` validated selected capabilities fields across HTTP and gateway, but did not explicitly assert parity for capabilities metadata (`api_version`, `schema_changelog`) in the healthy baseline scenario.

## Evidence

- Existing `test_capabilities_parity_for_shared_backend_and_tiers` compared backend/tiers/obsidian tools only.
- Metadata drift risk remained mostly covered by static guardrails, not by direct runtime parity assertion.

## Decision

- Extended healthy-path transport parity test with explicit assertions for:
  - `api_version` parity
  - `schema_changelog` parity
  - full `health` parity and expected healthy component states

## Risk

- Low: test-only change.
- Positive: stronger runtime parity signal for capabilities response across transports.

## Validation

- `unified/.venv/bin/pytest -q unified/tests/test_transport_parity.py`
- `make pr-readiness`

## Files

- `unified/tests/test_transport_parity.py`
- `docs/archive/iterations/2026-04-09/ITERATION_REPORT_2026-04-09_17.md`
