# Iteration Report 23 (2026-04-08)

## Stream
Observability i health truthfulness (release gate enforcement)

## Problem
Release-gate check był uruchamiany w CI w trybie audit-only, więc drift polityki branch protection był wykrywany, ale nie blokował merge.

## Evidence
- W `unified-smoke.yml` krok guardrails uruchamiał `check_release_gate.py` z `RELEASE_GATE_ENFORCE=0`.

## Decision
- Przełączono CI guardrail na enforce:
  - `.github/workflows/unified-smoke.yml`
  - `RELEASE_GATE_ENFORCE=1`
  - `GH_TOKEN: ${{ github.token }}`
- Zaktualizowano manual operacyjny o informację, że `Unified Smoke Tests / guardrails` egzekwuje release gate.

## Validation
- Lokalne sprawdzenie:
  - `RELEASE_GATE_ENFORCE=1 python3 scripts/check_release_gate.py` -> **OK**
- Repo-level branch protection jest już aktywne i zgodne z wymaganym zestawem checków.

## Risk
- Średni operacyjnie: niezgodność branch protection z polityką będzie teraz failować CI (intencjonalne zachowanie governance).

## Status
**fixed**
