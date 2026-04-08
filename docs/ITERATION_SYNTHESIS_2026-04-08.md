# Iteration Synthesis (2026-04-08)

## Scope

Syntetyczny raport po serii iteracyjnych porcji napraw realizowanych wg modelu:
`diagnoza -> decyzja -> naprawa -> walidacja -> raport cząstkowy`.

Raport obejmuje głównie iteracje:
- 18–19 (release gate telemetry + execution),
- 20–22 (adapter migration do use-cases + boundary guard),
- 23 (release gate enforcement in CI),
- 24–25 (cross-transport capabilities/operation parity),
- 26 (cleanup register i higiena repo),
- 27 (audit semantics hardening for `updated_by` at API boundary),
- 28–29 (Obsidian capabilities normalization + response contract),
- 30–32 (cleanup pass etap 1 + repo hygiene CI guardrail),
- 33–34 (capabilities metadata parity + dedup into shared contract),
- 35–46 (archive cleanup + legacy docs archiving + component-level health contract + API health fallback + truthfulness guardrail + audit-semantics guardrail + Obsidian contract guardrail + local guardrails runner + CI runner tests + local PR-readiness bundle + merge-readiness snapshot).

## Current platform state

- **Release gate**: aktywny i egzekwowany (`master` protected + required checks + CI enforce).
- **Capabilities truthfulness**: `brain_capabilities` raportuje backend health w obu transportach.
- **Cross-transport parity**: parity testy obejmują core + dodatkowo `sync_check`, `upsert_bulk`, `maintain`.
- **Use-case boundary**: adaptery V1 dla zmigrowanych ścieżek write korzystają z `use_cases`.
- **Contracts**: wspólne kontrakty (manifest/requests/limits/errors/paths) są testowane integrity testami.
- **Capabilities contract**: wspólny kontrakt odpowiedzi i metadanych capabilities jest testowany i egzekwowany w CI.
- **Component health truthfulness**: capabilities zawiera teraz `health.overall` oraz `health.components` (api/db/vector_store/obsidian).
- **Probe robustness**: po niepowodzeniu `/readyz` i `/healthz` capabilities wykonuje fallback do `/api/v1/health` przed oznaczeniem `unavailable`.
- **CI truthfulness gate**: smoke guardrails uruchamiają `scripts/check_capabilities_truthfulness.py` dla szybkiego wykrycia dryfu kontraktu/statusu.
- **CI audit gate**: smoke guardrails uruchamiają `scripts/check_audit_semantics.py` dla szybkiego wykrycia dryfu semantyki `created_by/updated_by`.
- **CI Obsidian gate**: smoke guardrails uruchamiają `scripts/check_obsidian_contract.py` dla szybkiego wykrycia dryfu feature-flag i kontraktu capabilities/tools.
- **Guardrails UX**: statyczne policy-checki są dostępne jako jedna komenda przez `scripts/check_local_guardrails.py`.
- **Guardrails CI depth**: job `guardrails` uruchamia też dedykowane testy runnerów policy-check.
- **PR readiness UX**: jedna lokalna komenda `python3 scripts/check_pr_readiness.py` (lub `make pr-readiness`) uruchamia guardrails + szybkie smoke policy/contract.
- **Merge decision artifact**: snapshot gotowości do merge jest utrzymywany w `docs/MERGE_READINESS_2026-04-08.md`.

## Confirmed problems

- Brak ochrony brancha `master` i brak egzekwowania release gate w CI.
- Rozjazd payloadu `brain_capabilities` (backend health obecny tylko w stdio).
- Częściowa migracja adapterów do `use_cases` (pozostałe direct imports).
- Brak testów parity dla części operacji Tier2/Tier3.
- Brak jawnego rejestru cleanupu dla artefaktów iteracyjnych.

## Rejected / narrowed problems

- Teza o całkowicie „martwym backendzie” została odrzucona: backend był operacyjnie dostępny, problem dotyczył głównie truthfulness raportowania i policy drift.
- Teza o konieczności dużego rewrite upfront została odrzucona: iteracyjne porcje dały szybszy i bezpieczniejszy efekt.

## Implemented fixes

- Branch protection ustawione i zweryfikowane przez `gh`.
- `scripts/check_release_gate.py` + CI enforce (`Unified Smoke / guardrails`).
- `mcp_transport.brain_capabilities` rozszerzone o backend probe (`readyz/healthz`).
- Rozszerzone parity tests (`test_transport_parity.py`) dla dodatkowych operacji.
- Rozszerzona warstwa `use_cases.memory` (`store_memories_many`, `run_maintenance`, `upsert_memories_bulk`) + przepięcie adapterów.
- Dodane boundary guard tests (`test_use_case_boundary.py`).
- Utworzony cleanup register (`docs/CLEANUP_REGISTER_2026-04-08.md`).
- Utwardzony kontrakt audit actor (`updated_by` override na granicy API PATCH).
- Dodany wspólny klucz `obsidian` w capabilities (transport-agnostyczny).
- Dodane kontrakty capabilities:
  - `capabilities_response_contract.json`
  - `capabilities_metadata.json`
- Dodany guardrail repo hygiene w CI (`scripts/check_repo_hygiene.py`).

## Deferred items (with rationale)

- **Full Obsidian live sync E2E on local vaults**: wymaga controlled runtime z odpowiednią konfiguracją środowiska i explicit scope operacyjnego.
- **Repo cleanup execution**: iteracyjne raporty i legacy plan/audit docs zostały zarchiwizowane; dalszy cleanup zależy od nowych artefaktów.
- **Doc consolidation** (duplikaty audytowe/plany): częściowo wykonane (iteracyjne raporty zarchiwizowane i zindeksowane), pozostały dokumenty audytowo-planistyczne do decyzji keep/archive.

## Residual operational risks

- Ryzyko szumu dokumentacyjnego jest obniżone po archiwizacji legacy docs, ale wymaga utrzymania dyscypliny dla nowych raportów.
- Utrzymywanie dwóch transportów nadal wymaga dyscypliny testowej (obecnie kontrolowane przez parity/integrity tests).
- Obsidian local path pozostaje zależny od konfiguracji środowiska i trybu uruchomienia.

## Next recommended actions

1. Wykonać finalny pass cleanup zgodnie z `docs/CLEANUP_REGISTER_2026-04-08.md` (doc consolidation + archiwizacja iteracji).
2. Ustalić doc policy: które raporty iteracyjne zostają, a które przechodzą do archiwum z jednym indeksem.
3. Uruchomić controlled Obsidian E2E (vault read/write/sync status) na jawnie zatwierdzonej konfiguracji.
