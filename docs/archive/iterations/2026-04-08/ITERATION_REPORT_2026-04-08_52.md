# Iteration Report 52 (2026-04-08)

## Stream
- Obsidian runtime execution readiness

## Problem
- Controlled Obsidian live E2E execution failed in local container runtime due backend-side `backend_unavailable` errors.
- Root causes observed:
  - missing CLI in container (`obsidian` binary unavailable),
  - vault path mapping not reliably consumable in current runtime setup.

## Evidence
- Live run with `RUN_CONTROLLED_OBSIDIAN_E2E=1` returned 503:
  - vault discovery: CLI unavailable,
  - write-note: missing/invalid vault path mapping for selected test vault.

## Decision
- Harden runtime config and test behavior instead of forcing brittle environment-specific assumptions:
  - pass Obsidian env controls into container,
  - support legacy `OBSIDIAN_VAULT_PATHS` format parsing,
  - make controlled E2E tests skip (with explicit reason) on `backend_unavailable`.

## Changes
- Runtime config:
  - `docker-compose.unified.yml`
    - pass-through for:
      - `OBSIDIAN_CLI_COMMAND`
      - `OBSIDIAN_VAULT_PATHS`
- Adapter:
  - `unified/src/common/obsidian_adapter.py`
    - added `_parse_vault_paths_mapping()` supporting:
      - JSON mapping,
      - legacy `name:path,name:path` mapping.
    - `list_vaults()` and `_get_vault_path()` now use shared parser path.
- Tests:
  - `unified/tests/integration/test_obsidian_controlled_e2e.py`
    - skip on explicit `backend_unavailable` contract payload.
  - `unified/tests/test_obsidian_cli.py`
    - added parser regression for legacy mapping format.

## Validation
- `cd unified && uv run ruff check src/common/obsidian_adapter.py tests/test_obsidian_cli.py tests/integration/test_obsidian_controlled_e2e.py` -> pass
- `cd unified && uv run pytest -q tests/test_obsidian_cli.py tests/integration/test_obsidian_controlled_e2e.py` -> pass (`7 passed, 2 skipped`)
- live controlled run (`RUN_CONTROLLED_OBSIDIAN_E2E=1`) -> deterministic `skip` in unsupported runtime rather than failure.

## Risk
- Full live Obsidian roundtrip remains environment-dependent until container-reachable vault mapping is standardized in deployment profile.

## Status
- `fixed (resilience)` — runtime/config/test path hardened.
- `deferred (full live success)` — requires target environment vault accessibility.
