# Iteration Report 22 (2026-04-08)

## Stream
Gateway/API contract consistency (boundary guardrails)

## Problem
Po migracji adapterów do `use_cases` brakowało testu strażnika, który wykrywa regresję importów (powrót do bezpośredniego użycia `memory_writes` w adapterach V1).

## Evidence
- Migracja była oparta na zmianie importów, które łatwo przypadkowo cofnąć podczas refaktorów.
- Brak testu statycznego pilnującego granicy adapter -> use-case.

## Decision
- Dodano testy boundary:
  - `unified/tests/test_use_case_boundary.py`
- Testy pilnują:
  - `api/v1/memory.py` używa `use_cases.memory` dla zmigrowanych write paths,
  - `api/v1/obsidian.py` używa `store_memories_many` z `use_cases`,
  - brak legacy importu `handle_memory_write_many` z `memory_writes`.

## Validation
- `./unified/.venv/bin/pytest -q unified/tests/test_use_case_boundary.py` -> **2 passed**
- `./unified/.venv/bin/pytest -q unified/tests/test_memory_use_cases.py unified/tests/test_use_case_boundary.py` -> **10 passed**

## Risk
- Bardzo niski: testy statyczne (string/source guards), bez wpływu na runtime.

## Status
**fixed**
