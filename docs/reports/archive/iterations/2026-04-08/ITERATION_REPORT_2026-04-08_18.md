# Iteration Report 18 (2026-04-08)

## Stream
Observability i health truthfulness (release gate telemetry)

## Problem
Mieliśmy opis polityki branch protection w dokumentacji, ale brakowało automatycznego, powtarzalnego checku operacyjnego, który wykrywa drift release gate.

## Evidence
- `gh api repos/<owner>/openbrain/branches/master/protection` zwraca `404` (branch niechroniony).
- Brak skryptu, który porównuje aktywną konfigurację protection z wymaganym zestawem checków.

## Decision
- Dodano skrypt audytowy:
  - `scripts/check_release_gate.py`
- Dodano trzy tryby logiczne:
  - wykrycie braku ochrony brancha,
  - wykrycie brakujących required checks,
  - tryb enforce przez `RELEASE_GATE_ENFORCE=1` (w audit mode domyślnie brak blokowania).
- Dodano uruchamianie w CI smoke:
  - `.github/workflows/unified-smoke.yml` (guardrails, audit-only).
- Uzupełniono manual operacyjny o komendy audit/enforce.

## Validation
- `python -m pytest -q unified/tests/test_release_gate_guardrail.py` -> oczekiwane przejście testów logiki (mockowane odpowiedzi GH).
- Manual check:
  - `python scripts/check_release_gate.py`
  - `RELEASE_GATE_ENFORCE=1 python scripts/check_release_gate.py`

## Risk
- Niski: nowy check jest domyślnie nieblokujący (audit-only) i nie wpływa na runtime API.

## Status
**fixed**
