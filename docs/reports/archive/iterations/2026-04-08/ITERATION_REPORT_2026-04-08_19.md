# Iteration Report 19 (2026-04-08)

## Stream
Observability i health truthfulness (governance execution)

## Problem
Repo miał zdefiniowaną docelową politykę release gate, ale branch `master` nie był faktycznie chroniony.

## Evidence
- Wcześniej `gh api repos/gniewkob/openbrain/branches/master/protection` zwracał `404`.
- `python scripts/check_release_gate.py` raportował brak protection i brakujące required checks.

## Decision
- Zastosowano branch protection przez `gh api` dla `master` z polityką:
  - required status checks (9 kontekstów),
  - `strict: true` (branch up to date),
  - wymagany PR review (`required_approving_review_count=1`),
  - `dismiss_stale_reviews: true`,
  - `enforce_admins: true`,
  - `required_conversation_resolution: true`,
  - force-push/delete disabled.

## Validation
- `gh api repos/gniewkob/openbrain/branches/master/protection` -> zwraca aktywną konfigurację ochrony.
- `python scripts/check_release_gate.py` -> `[OK] Branch protection enabled with 9 checks.`
- `RELEASE_GATE_ENFORCE=1 python scripts/check_release_gate.py` -> `EXIT:0`.

## Risk
- Średni operacyjnie: merge do `master` wymaga teraz przejścia wskazanych checków i review (bardziej restrykcyjny workflow, ale zgodny z governance).

## Status
**fixed**
