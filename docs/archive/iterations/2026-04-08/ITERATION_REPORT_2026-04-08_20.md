# Iteration Report 20 (2026-04-08)

## Stream
Gateway/API contract consistency (adapter migration to use-cases)

## Problem
Batch write adapters (`/api/v1/memory/write-many` and `/api/v1/obsidian/sync`) nadal wywoływały niskopoziomowe `memory_writes` bezpośrednio, mimo że warstwa `use_cases` była już wprowadzona jako docelowa granica orkiestracji.

## Evidence
- `api/v1/memory.py` importował `handle_memory_write_many` z `memory_writes`.
- `api/v1/obsidian.py` importował `handle_memory_write_many` z `memory_writes`.
- Wcześniejsze iteracje oznaczyły „Adapter migration to use-cases” jako `deferred`.

## Decision
- Dodano use-case:
  - `store_memories_many(session, req, actor)` w `src/use_cases/memory.py`.
- Przepięto adaptery V1 na warstwę use-cases:
  - `src/api/v1/memory.py`
  - `src/api/v1/obsidian.py`
- Utrzymano zachowanie 1:1 (delegacja do istniejącego write engine, bez zmiany kontraktu API).

## Validation
- `./unified/.venv/bin/pytest -q unified/tests/test_memory_use_cases.py` -> **6 passed**
- `./unified/.venv/bin/pytest -q unified/tests/test_route_registration.py` -> **5 passed**
- `./unified/.venv/bin/pytest -q unified/tests/test_endpoints_summary.py -k "v1_write or v1_find or v1_get_context"` -> **4 passed**

## Risk
- Niski: zmiana dotyczy warstwy orkiestracji i importów; brak zmiany schematów i payloadów HTTP.

## Status
**fixed**
