# Iteration Report 21 (2026-04-08)

## Stream
Gateway/API contract consistency (adapter migration to use-cases, etap 2)

## Problem
Po migracji ścieżek `write-many` pozostały kolejne adaptery V1, które nadal odwoływały się bezpośrednio do `memory_writes` (`maintain`, `bulk-upsert`), co utrzymywało niespójny punkt wejścia aplikacyjnego.

## Evidence
- `src/api/v1/memory.py` używał bezpośrednio `run_maintenance` i `upsert_memories_bulk` z `memory_writes`.
- W `use_cases.memory` brakowało wrapperów dla tych dwóch operacji.

## Decision
- Rozszerzono warstwę `use_cases` o:
  - `run_maintenance(session, req, actor)`
  - `upsert_memories_bulk(session, items)`
- Przepięto endpointy V1 do tych wrapperów:
  - `src/api/v1/memory.py`
- Utrzymano semantykę 1:1 (wrappery delegują do istniejących implementacji write-side).
- Dodano testy delegacji wrapperów:
  - `unified/tests/test_memory_use_cases.py`

## Validation
- `./unified/.venv/bin/pytest -q unified/tests/test_memory_use_cases.py` -> **8 passed**
- `./unified/.venv/bin/pytest -q unified/tests/test_endpoints_summary.py -k "bulk_upsert or maintain or write_many"` -> **1 passed**

## Risk
- Niski: zmiana architektury wewnętrznej (punkt wejścia), bez zmiany zewnętrznych kontraktów endpointów.

## Status
**fixed**
