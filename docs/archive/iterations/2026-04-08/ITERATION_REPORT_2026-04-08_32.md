# Iteration Report 32 (2026-04-08)

## Stream
Performance i cleanups (hygiene guardrail automation)

## Problem
Cleanup był wykonywany ręcznie, ale brakowało automatycznego guardraila, który blokuje powrót znanych artefaktów debug do repo.

## Evidence
- Artefakt `reproduce_hang.py` został wcześniej wykryty i usunięty ręcznie.
- Brak CI checku, który utrzymuje ten stan w czasie.

## Decision
- Dodano skrypt:
  - `scripts/check_repo_hygiene.py`
- Skrypt sprawdza deny-list znanych artefaktów debug i failuje przy naruszeniu.
- Dodano uruchamianie guardraila w:
  - `.github/workflows/unified-smoke.yml` (`guardrails` job)
- Uzupełniono operating manual.

## Validation
- `python3 scripts/check_repo_hygiene.py` -> **Repository hygiene check passed.**

## Risk
- Bardzo niski: prosty check read-only, brak wpływu na runtime.

## Status
**fixed**
