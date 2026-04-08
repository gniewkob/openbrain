# Iteration Report 36 (2026-04-08)

## Stream
Obsidian integration (controlled E2E harness bootstrap)

## Problem
Obsidian live E2E było odłożone jako `deferred`, a repo nie miało bezpiecznego harnessu do kontrolowanego uruchamiania testu środowiskowego z explicit opt-in.

## Evidence
- Brak dedykowanego testu integracyjnego, który:
  - domyślnie się skipuje,
  - uruchamia się tylko po świadomym ustawieniu env.

## Decision
- Dodano controlled E2E harness:
  - `unified/tests/integration/test_obsidian_controlled_e2e.py`
- Test domyślnie skipuje, uruchamia się po:
  - `RUN_CONTROLLED_OBSIDIAN_E2E=1`
- Weryfikuje read-only discovery (`/api/v1/obsidian/vaults`) i opcjonalnie asercję wybranego vaultu (`OBSIDIAN_TEST_VAULT`).
- Zaktualizowano docs:
  - `docs/operating-manual.md` (sekcja Test Posture).
- Zarejestrowano marker pytest `integration` w:
  - `unified/pyproject.toml`

## Validation
- `./unified/.venv/bin/pytest -q unified/tests/integration/test_obsidian_controlled_e2e.py` -> **1 skipped** (expected without opt-in)

## Risk
- Niski: test jest opt-in i read-only; nie wpływa na runtime ani domyślny CI path.

## Status
**fixed**
