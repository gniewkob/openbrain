# Iteration Report 50 (2026-04-08)

## Stream
- Obsidian integration resilience

## Problem
- `ObsidianCliAdapter.list_vaults()` depended entirely on CLI availability.
- In local/governed environments with configured vault paths but missing CLI binary, vault discovery failed hard instead of degrading gracefully.

## Evidence
- `list_vaults()` called `_run("vaults")` without env-based fallback.
- Adapter already supported env-based vault paths for file operations (`OBSIDIAN_VAULT_PATHS`, `OBSIDIAN_VAULT_<NAME>_PATH`), but discovery path did not reuse that capability.

## Decision
- Add an env-based fallback for vault discovery:
  - parse configured vault names from `OBSIDIAN_VAULT_PATHS`,
  - parse named mappings from `OBSIDIAN_VAULT_<NAME>_PATH`,
  - if CLI call fails and configured vaults exist, return configured vaults instead of failing.

## Changes
- Runtime:
  - `unified/src/common/obsidian_adapter.py`
    - added `_configured_vault_names_from_env()`,
    - updated `list_vaults()` to merge CLI names with configured names and to fallback on `ObsidianCliError`.
- Tests:
  - `unified/tests/test_obsidian_cli.py`
    - added vault-env parsing coverage,
    - added async fallback behavior tests for CLI unavailable path.

## Validation
- `cd unified && uv run ruff check src/common/obsidian_adapter.py tests/test_obsidian_cli.py` -> pass
- `cd unified && uv run pytest -q tests/test_obsidian_cli.py` -> pass (`6 passed`)
- `python3 scripts/check_pr_readiness.py` -> pass

## Risk
- Env-derived names from `OBSIDIAN_VAULT_<NAME>_PATH` normalize underscores to spaces; display naming may differ from user-facing canonical names but does not affect path mapping logic.

## Status
- `fixed` — Obsidian vault discovery is now resilient to missing CLI when env mapping is present.
