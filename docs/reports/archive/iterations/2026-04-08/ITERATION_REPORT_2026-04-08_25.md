# Iteration Report 25 (2026-04-08)

## Stream
Gateway/API contract consistency (cross-transport parity beyond capabilities)

## Problem
Mieliśmy testową parity głównie dla podstawowych operacji i capabilities, ale bez pełnej osłony dla operacji administracyjnych/sync (`sync_check`, `upsert_bulk`, `maintain`), co zostawiało ryzyko cichego driftu między stdio gateway i HTTP MCP transport.

## Evidence
- Poprzednie testy parity obejmowały głównie: `store`, `list`, `get`, `search`, `update`, `delete`.
- Brak parity assertions dla części operacji Tier 2 / Tier 3.

## Decision
- Rozszerzono testy parity w:
  - `unified/tests/test_transport_parity.py`
- Dodano scenariusze porównawcze:
  - `brain_sync_check`
  - `brain_upsert_bulk`
  - `brain_maintain`
- Zaktualizowano fake klientów testowych o odpowiedzi dla endpointów:
  - `/api/v1/memory/sync-check`
  - `/api/v1/memory/bulk-upsert`
  - `/api/v1/memory/maintain`

## Validation
- `./unified/.venv/bin/pytest -q unified/tests/test_transport_parity.py` -> **10 passed**

## Risk
- Bardzo niski: zmiana testowa, brak wpływu na runtime.

## Status
**fixed**
