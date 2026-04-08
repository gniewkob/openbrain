# Iteration Report 53 (2026-04-08)

## Stream
- Obsidian controlled live E2E execution closure

## Problem
- Controlled Obsidian E2E had coverage and resilience guards, but final live success criterion remained open in merge readiness.

## Evidence
- Previous runs in default runtime returned `backend_unavailable` due env/runtime mismatch.
- After runtime hardening, explicit isolated mapping became feasible.

## Decision
- Execute controlled live E2E on isolated vault path reachable from container runtime:
  - host path: `unified/.controlled-vault`
  - container path: `/app/.controlled-vault`
  - env override: `OBSIDIAN_VAULT_PATHS={"Controlled E2E":"/app/.controlled-vault"}`
- Preserve safety:
  - no write into user’s real Obsidian vaults,
  - dedicated test note path `OpenBrain Controlled E2E/roundtrip.md`.

## Changes
- Runtime orchestration:
  - `start_unified.sh` now preserves explicit shell overrides after `.env` load for:
    - `OBSIDIAN_VAULT_PATHS`
    - `OBSIDIAN_CLI_COMMAND`
    - `ENABLE_NGROK`
- Adapter parsing:
  - `unified/src/common/obsidian_adapter.py`
    - legacy mapping parser accepts braced form (`{name:path,...}`) and quoted entries.
- Tests:
  - `unified/tests/test_obsidian_cli.py`
    - added parser regression for braced legacy format.

## Validation
- Unit/static:
  - `cd unified && uv run ruff check src/common/obsidian_adapter.py tests/test_obsidian_cli.py` -> pass
  - `cd unified && uv run pytest -q tests/test_obsidian_cli.py` -> pass (`8 passed`)
- Live controlled E2E:
  - `docker exec openbrain-unified-server env | grep ^OBSIDIAN` confirms runtime mapping
  - `cd unified && RUN_CONTROLLED_OBSIDIAN_E2E=1 ... uv run pytest -q tests/integration/test_obsidian_controlled_e2e.py -v` -> pass (`2 passed`)

## Risk
- Controlled live success depends on explicit runtime mapping profile; deployments without container-reachable vault paths will correctly fall back to guarded skip/error behavior.

## Status
- `fixed` — controlled Obsidian live E2E success criterion closed.
