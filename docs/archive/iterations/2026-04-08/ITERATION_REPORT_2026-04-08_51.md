# Iteration Report 51 (2026-04-08)

## Stream
- Obsidian controlled E2E hardening

## Problem
- Controlled Obsidian E2E coverage only validated vault discovery and did not exercise write/read/sync roundtrip.
- Deferred item required stronger runtime path confidence before executing in approved environment.

## Evidence
- `unified/tests/integration/test_obsidian_controlled_e2e.py` contained discovery-only scenario.

## Decision
- Extend controlled E2E integration test with a gated roundtrip scenario (write -> read -> sync) under existing opt-in flag.
- Keep execution safe-by-default:
  - tests remain skipped unless `RUN_CONTROLLED_OBSIDIAN_E2E=1`,
  - runtime targets are provided explicitly via env (`OPENBRAIN_BASE_URL`, `OBSIDIAN_TEST_VAULT`, optional `INTERNAL_API_KEY`).

## Changes
- `unified/tests/integration/test_obsidian_controlled_e2e.py`
  - added `test_obsidian_controlled_note_roundtrip()`:
    - writes controlled note (`/api/v1/obsidian/write-note`),
    - reads it back (`/api/v1/obsidian/read-note`),
    - syncs deterministic path (`/api/v1/obsidian/sync`),
    - validates payload invariants.
- `docs/MERGE_READINESS_2026-04-08.md`
  - deferred note clarified: coverage exists; execution pending explicit environment approval.

## Validation
- `cd unified && uv run ruff check tests/integration/test_obsidian_controlled_e2e.py` -> pass
- `cd unified && uv run pytest -q tests/integration/test_obsidian_controlled_e2e.py` -> pass (`2 skipped` as expected without opt-in env)

## Risk
- Roundtrip test writes a note when enabled; must target dedicated controlled vault/path in execution environment.

## Status
- `fixed (coverage)` — controlled roundtrip scenario implemented.
- `deferred (execution)` — live run still requires explicit env approval and target variables.
